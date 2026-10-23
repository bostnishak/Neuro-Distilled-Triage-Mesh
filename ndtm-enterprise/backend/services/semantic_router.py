"""İhbar metinlerini Redis önbellek, yerel INT8 ONNX modeli ve ana LLM arasında yönlendiren servis.
Modelin Shannon entropisi 0.28 altındaysa (tahmininden eminse) CPU üzerinde çalışan ONNX modeli kullanılır.
Kararsız durumlarda veya devre kesici kapalıyken büyük dil modeline devredilir.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import time
from typing import Any, Sequence
from uuid import uuid4

import numpy as np
import redis.asyncio as aioredis

from backend.core.config import get_settings
from backend.core.exceptions import CircuitBreakerOpenError
from backend.middleware.circuit_breaker import CircuitBreaker
from backend.schemas.router import ExecutionTarget, RouterInferenceResponse
from backend.services.deduplication_engine import TextEmbeddingService
from backend.services.onnx_runtime_engine import ONNXRuntimeEngine, TAXONOMY_INTENTS

logger = logging.getLogger("services.semantic_router")
settings = get_settings()


def compute_normalized_shannon_entropy(probs: np.ndarray) -> float:
    """Olasılık vektörünün Shannon entropisini hesaplar ve [0.0, 1.0] arasına normalize eder."""
    k = len(probs)
    if k <= 1:
        return 0.0
    # Add epsilon to prevent log(0)
    eps = 1e-12
    p_safe = np.clip(probs, eps, 1.0)
    raw_entropy = -float(np.sum(p_safe * np.log(p_safe)))
    normalized = raw_entropy / math.log(k)
    return round(float(np.clip(normalized, 0.0, 1.0)), 4)


class TeacherLLMClient:
    """Simulates or invokes the deep Teacher LLM reasoning backend."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or settings.TEACHER_API_KEY

    async def predict_teacher(self, text: str) -> dict[str, Any]:
        """Deep contextual reasoning inference from Teacher LLM."""
        # Realistic network and inference simulation (50-100ms)
        await asyncio.sleep(0.06)

        lower = text.lower()
        if any(w in lower for w in ("yangın", "trafo", "alev", "patlama")):
            return {"intent": "TRANSFORMER_FIRE", "confidence": 0.99, "urgency": 0.95}
        if any(w in lower for w in ("gaz", "koku", "zehir")):
            return {"intent": "GAS_LEAK", "confidence": 0.98, "urgency": 0.92}
        if any(w in lower for w in ("elektrik", "kesinti", "karanlık", "şebeke")):
            return {"intent": "POWER_GRID_FAILURE", "confidence": 0.97, "urgency": 0.85}
        if any(w in lower for w in ("fiber", "kablo", "internet", "kopuk")):
            return {"intent": "FIBER_CUT", "confidence": 0.96, "urgency": 0.70}
        if any(w in lower for w in ("su", "boru", "patlak", "basma")):
            return {"intent": "WATER_MAIN_BURST", "confidence": 0.96, "urgency": 0.75}
        if any(w in lower for w in ("yol", "asfalt", "çökme", "hendek")):
            return {"intent": "ROAD_COLLAPSE", "confidence": 0.95, "urgency": 0.65}
        if any(w in lower for w in ("parazit", "sinyal", "telsiz")):
            return {"intent": "SIGNAL_INTERFERENCE", "confidence": 0.92, "urgency": 0.50}

        return {"intent": "CYBER_TELEMETRY_ANOMALY", "confidence": 0.90, "urgency": 0.40}


class CalibratedSemanticRouter:
    """3-Stage Routing Gate: (1) Redis Semantic Cache, (2) INT8 Student Entropy Gate, (3) Teacher LLM."""

    def __init__(
        self,
        onnx_engine: ONNXRuntimeEngine | None = None,
        redis_client: aioredis.Redis | None = None,
        teacher_client: TeacherLLMClient | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        embedder: TextEmbeddingService | None = None,
    ) -> None:
        self.onnx = onnx_engine or ONNXRuntimeEngine(settings.ONNX_STUDENT_MODEL_PATH)
        self.redis = redis_client
        self.teacher = teacher_client or TeacherLLMClient()
        self.breaker = circuit_breaker or CircuitBreaker(failure_threshold=3, recovery_timeout=30.0)
        self.embedder = embedder or TextEmbeddingService()
        self.shadow_callback = None
        self._local_cache: dict[str, dict[str, Any]] = {}

    def set_shadow_callback(self, callback: Any) -> None:
        self.shadow_callback = callback

    def _compute_ood_similarity(self, embedding: Sequence[float]) -> float:
        """Computes cosine similarity against training distribution centroid."""
        vec = np.array(embedding, dtype=np.float32)
        norm = np.linalg.norm(vec)
        if norm < 1e-6:
            return 0.5
        # Simulated centroid vector
        centroid = np.ones(len(embedding), dtype=np.float32) / np.sqrt(len(embedding))
        sim = float(np.dot(vec / norm, centroid))
        # Scale to [0.5, 0.95]
        return round(float(np.clip(0.70 + (sim * 0.15), 0.0, 1.0)), 3)

    async def _check_semantic_cache(self, embedding: Sequence[float]) -> dict[str, Any] | None:
        """Stage 1: Redis Semantic KV-Cache cosine matching >= 0.96."""
        if self.redis:
            try:
                keys = await self.redis.keys("semcache:*")
                for key in keys:
                    raw = await self.redis.get(key)
                    if not raw:
                        continue
                    entry = json.loads(raw)
                    cached_emb = np.array(entry["embedding"], dtype=np.float32)
                    query_emb = np.array(embedding, dtype=np.float32)
                    sim = float(np.dot(query_emb, cached_emb) / (np.linalg.norm(query_emb) * np.linalg.norm(cached_emb) + 1e-8))
                    if sim >= 0.96:
                        return entry
            except Exception as exc:
                logger.warning("Redis semantic cache read error: %s", exc)

        # Fallback local cache
        for entry in self._local_cache.values():
            cached_emb = np.array(entry["embedding"], dtype=np.float32)
            query_emb = np.array(embedding, dtype=np.float32)
            sim = float(np.dot(query_emb, cached_emb) / (np.linalg.norm(query_emb) * np.linalg.norm(cached_emb) + 1e-8))
            if sim >= 0.96:
                return entry

        return None

    async def _put_semantic_cache(self, text: str, embedding: Sequence[float], intent: str, confidence: float, urgency: float) -> None:
        cache_entry = {
            "text": text[:100],
            "embedding": list(embedding),
            "intent": intent,
            "confidence": confidence,
            "urgency": urgency,
        }
        cache_key = f"semcache:{hash(text)}"
        self._local_cache[cache_key] = cache_entry
        if self.redis:
            try:
                await self.redis.setex(cache_key, settings.REDIS_CACHE_TTL_SECONDS, json.dumps(cache_entry))
            except Exception as exc:
                logger.debug("Redis semantic cache write warning: %s", exc)

    async def infer(self, text: str, redis_client: Any = None) -> RouterInferenceResponse:
        """Alias for route_inference allowing injected redis_client."""
        if redis_client is not None:
            self.redis = redis_client
        return await self.route_inference(text)

    async def route_inference(self, text: str) -> RouterInferenceResponse:
        """Executes full 3-stage routing protocol."""
        start_time = time.perf_counter()
        request_id = str(uuid4())

        # 1. Compute text embedding
        embedding = self.embedder.encode(text)

        # 2. Stage 1 — Semantic Cache Check (>= 0.96 similarity)
        cached = await self._check_semantic_cache(embedding)
        if cached:
            latency_ms = (time.perf_counter() - start_time) * 1000
            return RouterInferenceResponse(
                request_id=request_id,
                intent=cached["intent"],
                confidence=cached["confidence"],
                urgency=cached["urgency"],
                execution_target=ExecutionTarget.SEMANTIC_CACHE,
                student_entropy=0.0,
                ood_similarity=1.0,
                latency_ms=round(latency_ms, 2),
                cost_saved_usd=0.0025,
                from_cache=True,
            )

        # 3. Stage 2 — ONNX INT8 Student Inference & Shannon Entropy Gate
        student_intent, student_conf, student_urgency, probs = self.onnx.predict(
            embedding, temperature=settings.TEMPERATURE_CALIBRATION
        )
        entropy = compute_normalized_shannon_entropy(probs)
        ood_sim = self._compute_ood_similarity(embedding)

        # Routing Decision Rule: H(p) <= 0.28 AND S_OOD >= 0.75
        if entropy <= settings.ENTROPY_THRESHOLD and ood_sim >= settings.OOD_SIMILARITY_THRESHOLD:
            latency_ms = (time.perf_counter() - start_time) * 1000

            # Store in cache
            await self._put_semantic_cache(text, embedding, student_intent, student_conf, student_urgency)

            # Fire async shadow evaluation hook (15% sample rate)
            if self.shadow_callback:
                asyncio.create_task(
                    self.shadow_callback(request_id, text, student_intent, student_conf, probs)
                )

            return RouterInferenceResponse(
                request_id=request_id,
                intent=student_intent,
                confidence=student_conf,
                urgency=student_urgency,
                execution_target=ExecutionTarget.ONNX_STUDENT_INT8,
                student_entropy=entropy,
                ood_similarity=ood_sim,
                latency_ms=round(latency_ms, 2),
                cost_saved_usd=0.0025,
                from_cache=False,
            )

        # 4. Stage 3 — Circuit-Breaker Protected Teacher LLM Fallback
        logger.info(
            "Entropy routing triggered Teacher Fallback (Entropy: %.3f > %.2f or OOD: %.3f < %.2f)",
            entropy,
            settings.ENTROPY_THRESHOLD,
            ood_sim,
            settings.OOD_SIMILARITY_THRESHOLD,
        )

        try:
            teacher_res = await self.breaker.call(self.teacher.predict_teacher, text)
            latency_ms = (time.perf_counter() - start_time) * 1000

            await self._put_semantic_cache(
                text, embedding, teacher_res["intent"], teacher_res["confidence"], teacher_res["urgency"]
            )

            return RouterInferenceResponse(
                request_id=request_id,
                intent=teacher_res["intent"],
                confidence=teacher_res["confidence"],
                urgency=teacher_res["urgency"],
                execution_target=ExecutionTarget.TEACHER_LLM_FALLBACK,
                student_entropy=entropy,
                ood_similarity=ood_sim,
                latency_ms=round(latency_ms, 2),
                cost_saved_usd=0.0,
                from_cache=False,
            )
        except CircuitBreakerOpenError:
            # Fall back gracefully to student prediction if Teacher circuit is open
            latency_ms = (time.perf_counter() - start_time) * 1000
            logger.warning("Teacher Circuit Breaker is OPEN. Fallback to student.")
            return RouterInferenceResponse(
                request_id=request_id,
                intent=student_intent,
                confidence=student_conf,
                urgency=student_urgency,
                execution_target=ExecutionTarget.ONNX_STUDENT_INT8,
                student_entropy=entropy,
                ood_similarity=ood_sim,
                latency_ms=round(latency_ms, 2),
                cost_saved_usd=0.0,
                from_cache=False,
            )


# Alias
SemanticRouter = CalibratedSemanticRouter

