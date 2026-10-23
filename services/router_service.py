"""Module 2 — DistillMesh Semantic Router & ONNX student inference.

Every inference request first hits the distilled INT8 ONNX *student*
(~2-8 ms on CPU, $0). The router then decides whether that answer can be
trusted or must be escalated to the *teacher* LLM:

    request ──► student (ONNX) ──► decide_route() ──► accept student      (~80% traffic)
                    │                    │
                    │                    └─► escalate to teacher LLM        (~20% traffic)
                    └── embedding ──► prototype similarity (OOD detector)

Escalation signals (any one triggers the teacher):
  * low softmax confidence          (< ROUTER_CONFIDENCE_THRESHOLD)
  * ambiguous top-2 margin          (< ROUTER_MARGIN_THRESHOLD)
  * "other"/unknown intent
  * input truncated by the student's max_length (long, complex reports)
  * out-of-distribution: cosine similarity of the request embedding to the
    nearest intent prototype is below the calibrated threshold

Graceful degradation: if the teacher is unavailable the student answer is
used (flagged `degraded=True`); if no student is trained yet, a keyword
heuristic keeps the pipeline functional.
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import UUID

import asyncpg
import numpy as np
from pydantic import BaseModel, Field

from core.config import Settings
from core.llm import LLMClient, LLMError
from core.taxonomy import (
    BIO_LABELS,
    ENTITY_TYPES,
    FALLBACK_INTENT,
    INTENT_DESCRIPTIONS,
    INTENTS,
    urgency_to_priority,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Models
# =============================================================================
class RouteTarget(str, Enum):
    STUDENT = "student"
    TEACHER = "teacher"
    HEURISTIC = "heuristic"


class EntitySpan(BaseModel):
    type: str
    text: str
    start: int | None = None
    end: int | None = None


class TriagePrediction(BaseModel):
    intent: str
    confidence: float = Field(ge=0, le=1)
    urgency: float = Field(ge=0, le=1)
    priority: int = Field(ge=1, le=4)
    entities: list[EntitySpan] = Field(default_factory=list)
    intent_distribution: dict[str, float] = Field(default_factory=dict)


class RoutedResult(BaseModel):
    prediction: TriagePrediction
    route: RouteTarget
    model_name: str
    latency_ms: float
    student_latency_ms: float | None = None
    ood_similarity: float | None = None
    reasons: list[str] = Field(default_factory=list)
    degraded: bool = False
    estimated_cost_usd: float = 0.0


@dataclass(slots=True)
class StudentOutput:
    prediction: TriagePrediction
    margin: float
    truncated: bool
    latency_ms: float


@dataclass(frozen=True, slots=True)
class RouterThresholds:
    confidence: float
    margin: float
    ood_similarity: float


# =============================================================================
# Pure helpers (unit-testable)
# =============================================================================
def softmax(logits: np.ndarray) -> np.ndarray:
    z = logits - np.max(logits)
    e = np.exp(z)
    return e / e.sum()


def decode_bio(label_ids: np.ndarray, offsets: np.ndarray, text: str,
               bio_labels: tuple[str, ...]) -> list[EntitySpan]:
    """Convert token-level BIO predictions into character spans."""
    spans: list[EntitySpan] = []
    cur_type: str | None = None
    cur_start = cur_end = 0

    def _flush() -> None:
        if cur_type is not None and cur_end > cur_start:
            spans.append(EntitySpan(type=cur_type, text=text[cur_start:cur_end].strip(),
                                    start=cur_start, end=cur_end))

    for label_id, (start, end) in zip(label_ids.tolist(), offsets.tolist(), strict=False):
        if start == end:  # special / padding token
            continue
        label = bio_labels[label_id] if 0 <= label_id < len(bio_labels) else "O"
        if label == "O":
            _flush()
            cur_type = None
            continue
        prefix, ent_type = label.split("-", 1)
        if prefix == "B" or ent_type != cur_type:
            _flush()
            cur_type, cur_start, cur_end = ent_type, start, end
        else:  # I- continuation
            cur_end = end
    _flush()
    return [s for s in spans if s.text]


def decide_route(student: StudentOutput | None, ood_similarity: float | None,
                 th: RouterThresholds) -> tuple[RouteTarget, list[str]]:
    """Core routing policy. Returns the target and the human-readable reasons."""
    if student is None:
        return RouteTarget.TEACHER, ["student_unavailable"]
    reasons: list[str] = []
    pred = student.prediction
    if pred.confidence < th.confidence:
        reasons.append(f"low_confidence:{pred.confidence:.2f}")
    if student.margin < th.margin:
        reasons.append(f"ambiguous_margin:{student.margin:.2f}")
    if pred.intent == FALLBACK_INTENT:
        reasons.append("unknown_intent")
    if student.truncated:
        reasons.append("input_truncated")
    if ood_similarity is not None and ood_similarity < th.ood_similarity:
        reasons.append(f"out_of_distribution:{ood_similarity:.2f}")
    if reasons:
        return RouteTarget.TEACHER, reasons
    return RouteTarget.STUDENT, ["confident_in_distribution"]


# =============================================================================
# Student (ONNX Runtime)
# =============================================================================
class StudentOnnxModel:
    """INT8 multi-task student: intent logits, urgency (sigmoid) and BIO entity logits."""

    CONFIG_FILE = "student_config.json"
    DEFAULT_ONNX_FILE = "model.int8.onnx"
    OUTPUT_NAMES = ["intent_logits", "urgency", "entity_logits"]

    def __init__(self, model_dir: Path, intra_op_threads: int) -> None:
        import onnxruntime as ort
        from transformers import AutoTokenizer

        cfg = json.loads((model_dir / self.CONFIG_FILE).read_text(encoding="utf-8"))
        self.intents: tuple[str, ...] = tuple(cfg["intents"])
        self.bio_labels: tuple[str, ...] = tuple(cfg["bio_labels"])
        self.max_length = int(cfg.get("max_length", 128))
        self.name: str = cfg.get("model_name", "distillmesh-student-int8")
        if self.intents != INTENTS or self.bio_labels != BIO_LABELS:
            logger.warning("Student taxonomy differs from core.taxonomy; retrain recommended")

        opts = ort.SessionOptions()
        opts.intra_op_num_threads = intra_op_threads
        opts.inter_op_num_threads = 1
        opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        onnx_path = model_dir / cfg.get("onnx_file", self.DEFAULT_ONNX_FILE)
        self._session = ort.InferenceSession(str(onnx_path), sess_options=opts,
                                             providers=["CPUExecutionProvider"])
        self._tokenizer = AutoTokenizer.from_pretrained(str(model_dir), use_fast=True)
        # HF fast tokenizers are not safe for concurrent calls ("Already borrowed").
        self._tok_lock = threading.Lock()
        self._warmup()
        logger.info("Student ONNX model loaded", extra={"model": self.name, "path": str(onnx_path)})

    @classmethod
    def try_load(cls, model_dir: str | Path, intra_op_threads: int) -> StudentOnnxModel | None:
        path = Path(model_dir)
        if not (path / cls.CONFIG_FILE).exists():
            logger.warning("No trained student at %s — router will use teacher/heuristic. "
                           "Run the distillation pipeline to enable the fast path.", path)
            return None
        try:
            return cls(path, intra_op_threads)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to load student ONNX model from %s", path)
            return None

    def _warmup(self) -> None:
        for _ in range(3):
            self.predict("Warm-up request: pothole on the main road near the school.")

    def predict(self, text: str) -> StudentOutput:
        started = time.perf_counter()
        with self._tok_lock:
            enc = self._tokenizer(text, truncation=True, max_length=self.max_length,
                                  return_offsets_mapping=True, return_tensors="np")
        offsets = enc["offset_mapping"][0]
        feeds = {
            "input_ids": enc["input_ids"].astype(np.int64),
            "attention_mask": enc["attention_mask"].astype(np.int64),
        }
        intent_logits, urgency, entity_logits = self._session.run(self.OUTPUT_NAMES, feeds)

        probs = softmax(intent_logits[0].astype(np.float64))
        order = np.argsort(probs)[::-1]
        top, second = int(order[0]), int(order[1]) if len(order) > 1 else int(order[0])
        urgency_val = float(np.clip(urgency.reshape(-1)[0], 0.0, 1.0))
        entities = decode_bio(entity_logits[0].argmax(-1), offsets, text, self.bio_labels)
        truncated = int(offsets[:, 1].max()) < len(text.rstrip())

        prediction = TriagePrediction(
            intent=self.intents[top],
            confidence=float(probs[top]),
            urgency=urgency_val,
            priority=urgency_to_priority(urgency_val),
            entities=entities,
            intent_distribution={self.intents[i]: round(float(probs[i]), 4) for i in order[:3]},
        )
        return StudentOutput(prediction=prediction, margin=float(probs[top] - probs[second]),
                             truncated=truncated, latency_ms=(time.perf_counter() - started) * 1000)


# =============================================================================
# Semantic prototypes (OOD detector)
# =============================================================================
class PrototypeIndex:
    """Per-intent embedding centroids computed from the distillation training set."""

    def __init__(self, intents: list[str], centroids: np.ndarray, threshold: float) -> None:
        self.intents = intents
        self.centroids = centroids / (np.linalg.norm(centroids, axis=1, keepdims=True) + 1e-12)
        self.threshold = threshold

    @classmethod
    def try_load(cls, path: Path, expected_embedding_model: str) -> PrototypeIndex | None:
        if not path.exists():
            return None
        try:
            data = np.load(path, allow_pickle=False)
            model = str(data["embedding_model"])
            if model != expected_embedding_model:
                logger.warning("Prototypes were built with %s but EMBEDDING_MODEL=%s; OOD check disabled",
                               model, expected_embedding_model)
                return None
            return cls([str(x) for x in data["intents"]], data["centroids"].astype(np.float32),
                       float(data["threshold"]))
        except Exception:  # noqa: BLE001
            logger.exception("Failed to load prototypes from %s", path)
            return None

    def nearest(self, embedding: np.ndarray) -> tuple[str, float]:
        v = embedding.astype(np.float32)
        v = v / (np.linalg.norm(v) + 1e-12)
        sims = self.centroids @ v
        idx = int(np.argmax(sims))
        return self.intents[idx], float(sims[idx])


# =============================================================================
# Teacher (LLM) and heuristic fallback
# =============================================================================
_TEACHER_SYSTEM = (
    "You are an expert triage analyst for municipal infrastructure and IT service desks.\n"
    "Classify the report and respond ONLY with JSON:\n"
    '{"intent": <one of INTENTS>, "intent_distribution": {<intent>: <prob>, ...}, '
    '"urgency": <float 0..1>, "entities": [{"type": "LOCATION"|"ASSET"|"HAZARD", "text": <exact substring>}]}\n'
    "Urgency scale: 1.0 = immediate danger to life; 0.7 = significant disruption; 0.4 = inconvenience; "
    "0.1 = cosmetic.\nINTENTS:\n" + "\n".join(f"- {k}: {v}" for k, v in INTENT_DESCRIPTIONS.items())
)


def coerce_prediction(data: dict[str, Any], text: str) -> TriagePrediction:
    """Validate/repair an LLM classification payload against the taxonomy."""
    intent = str(data.get("intent", FALLBACK_INTENT)).strip().lower()
    if intent not in INTENTS:
        intent = FALLBACK_INTENT

    dist_raw = data.get("intent_distribution") or {}
    dist: dict[str, float] = {}
    if isinstance(dist_raw, dict):
        for k, v in dist_raw.items():
            if k in INTENTS and isinstance(v, (int, float)) and v >= 0:
                dist[k] = float(v)
    total = sum(dist.values())
    dist = {k: round(v / total, 4) for k, v in dist.items()} if total > 0 else {intent: 1.0}

    try:
        urgency = float(np.clip(float(data.get("urgency", 0.5)), 0.0, 1.0))
    except (TypeError, ValueError):
        urgency = 0.5

    entities: list[EntitySpan] = []
    lower = text.lower()
    for ent in data.get("entities") or []:
        if not isinstance(ent, dict):
            continue
        etype, etext = str(ent.get("type", "")).upper(), str(ent.get("text", "")).strip()
        if etype not in ENTITY_TYPES or not etext:
            continue
        pos = lower.find(etext.lower())
        entities.append(EntitySpan(type=etype, text=etext, start=pos if pos >= 0 else None,
                                   end=pos + len(etext) if pos >= 0 else None))

    return TriagePrediction(intent=intent, confidence=float(dist.get(intent, 0.9)), urgency=urgency,
                            priority=urgency_to_priority(urgency), entities=entities,
                            intent_distribution=dist)


class TeacherClassifier:
    def __init__(self, llm: LLMClient, cost_per_call: float) -> None:
        from middleware.resiliency import CircuitBreaker
        self._llm = llm
        self.cost_per_call = cost_per_call
        self.circuit_breaker = CircuitBreaker("teacher_llm", failure_threshold=3, recovery_timeout=30.0)

    @property
    def available(self) -> bool:
        from middleware.resiliency import CircuitState
        return self._llm.available and self.circuit_breaker.state != CircuitState.OPEN

    @property
    def name(self) -> str:
        return f"teacher:{self._llm.model}"

    async def _raw_predict(self, text: str) -> TriagePrediction:
        data = await self._llm.chat_json(
            [{"role": "system", "content": _TEACHER_SYSTEM}, {"role": "user", "content": text[:6000]}],
            temperature=0.0, max_tokens=600,
        )
        return coerce_prediction(data, text)

    async def predict(self, text: str) -> TriagePrediction:
        return await self.circuit_breaker.call(self._raw_predict, text)



class HeuristicClassifier:
    """Keyword fallback so the pipeline works before any model is trained."""

    name = "heuristic-keywords-v1"
    _KEYWORDS: dict[str, tuple[str, ...]] = {
        "road_damage": ("pothole", "crack", "asphalt", "sinkhole", "pavement", "road damage", "sidewalk"),
        "water_leak": ("leak", "burst pipe", "water main", "sewage", "hydrant", "flooding"),
        "power_outage": ("power outage", "blackout", "no electricity", "power cut", "transformer", "power line"),
        "streetlight_failure": ("streetlight", "street light", "lamp post", "lamppost", "light pole"),
        "waste_management": ("garbage", "trash", "waste", "dumpster", "litter", "rubbish", "bin"),
        "public_safety_hazard": ("exposed wire", "fallen tree", "collapsed", "gas smell", "smell of gas",
                                 "fire", "dangerous", "hazard"),
        "traffic_signal_failure": ("traffic light", "traffic signal", "signal not working", "pedestrian signal"),
        "it_service_request": ("password", "laptop", "vpn", "email", "printer", "server", "login", "wifi"),
    }
    _URGENT = ("fire", "gas", "injur", "electrocut", "collapse", "sparking", "exposed wire", "emergency",
               "bleeding", "trapped", "flood", "child", "hospital")

    def predict(self, text: str) -> TriagePrediction:
        lower = text.lower()
        scores = {intent: sum(kw in lower for kw in kws) for intent, kws in self._KEYWORDS.items()}
        best, hits = max(scores.items(), key=lambda kv: kv[1])
        intent = best if hits > 0 else FALLBACK_INTENT
        urgent_hits = sum(kw in lower for kw in self._URGENT)
        urgency = float(min(0.35 + 0.25 * urgent_hits, 1.0))
        return TriagePrediction(intent=intent, confidence=0.55 if hits else 0.3, urgency=urgency,
                                priority=urgency_to_priority(urgency), intent_distribution={intent: 1.0})


# =============================================================================
# Metrics
# =============================================================================
class RouterMetrics:
    """In-process rolling metrics (per replica). Fleet-wide metrics come from `inference_logs`."""

    def __init__(self, window: int = 2000) -> None:
        self._lat: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=window))
        self._counts: Counter[str] = Counter()
        self._cost = 0.0
        self._lock = threading.Lock()

    def record(self, route: RouteTarget, latency_ms: float, cost: float) -> None:
        with self._lock:
            self._counts[route.value] += 1
            self._lat[route.value].append(latency_ms)
            self._cost += cost

    def snapshot(self, teacher_cost_per_call: float) -> dict[str, Any]:
        with self._lock:
            total = sum(self._counts.values())
            routes = {}
            for route, count in self._counts.items():
                lat = np.asarray(self._lat[route]) if self._lat[route] else np.zeros(1)
                routes[route] = {
                    "requests": count,
                    "share": round(count / total, 4) if total else 0.0,
                    "p50_latency_ms": round(float(np.percentile(lat, 50)), 3),
                    "p95_latency_ms": round(float(np.percentile(lat, 95)), 3),
                }
            offloaded = total - self._counts.get(RouteTarget.TEACHER.value, 0)
            return {"total_requests": total, "routes": routes, "total_cost_usd": round(self._cost, 6),
                    "estimated_savings_usd": round(offloaded * teacher_cost_per_call, 6)}


# =============================================================================
# Router
# =============================================================================
class SemanticRouter:
    """DistillMesh proxy deciding student vs. teacher per request."""

    def __init__(self, settings: Settings, llm: LLMClient, student: StudentOnnxModel | None,
                 prototypes: PrototypeIndex | None) -> None:
        self._s = settings
        self.student = student
        self.prototypes = prototypes
        self.teacher = TeacherClassifier(llm, settings.teacher_cost_per_call_usd)
        self.heuristic = HeuristicClassifier()
        self.metrics = RouterMetrics()
        if settings.router_ood_threshold is not None:
            ood = settings.router_ood_threshold
        else:
            ood = prototypes.threshold if prototypes else 0.0
        self.thresholds = RouterThresholds(settings.router_confidence_threshold,
                                           settings.router_margin_threshold, ood)
        self.shadow_evaluator: Any | None = None

    @classmethod
    def from_settings(cls, settings: Settings, llm: LLMClient) -> SemanticRouter:
        student = StudentOnnxModel.try_load(settings.student_model_dir, settings.onnx_intra_op_threads)
        prototypes = PrototypeIndex.try_load(Path(settings.student_model_dir) / "prototypes.npz",
                                             settings.embedding_model)
        return cls(settings, llm, student, prototypes)

    async def infer(self, text: str, embedding: np.ndarray | None = None) -> RoutedResult:
        from middleware.resiliency import CircuitBreakerOpenError
        from middleware.telemetry_and_security import (
            ONNX_INFERENCE_DURATION_SECONDS,
            ROUTER_INFERENCES_TOTAL,
        )
        from core.logging_config import request_id_ctx

        started = time.perf_counter()
        student_out: StudentOutput | None = None
        if self.student is not None:
            try:
                student_out = await asyncio.to_thread(self.student.predict, text)
            except Exception:  # noqa: BLE001
                logger.exception("Student inference failed; escalating")

        ood_sim: float | None = None
        if embedding is not None and self.prototypes is not None:
            _, ood_sim = self.prototypes.nearest(embedding)

        target, reasons = decide_route(student_out, ood_sim, self.thresholds)
        prediction: TriagePrediction
        route, model_name, degraded, cost = target, "", False, 0.0

        if target is RouteTarget.STUDENT and student_out is not None and self.student is not None:
            prediction, model_name = student_out.prediction, self.student.name
            # Record Prometheus latency metric for ONNX student
            ONNX_INFERENCE_DURATION_SECONDS.labels(model_name=self.student.name).observe(
                student_out.latency_ms / 1000.0
            )
            # Continuous Evaluation: Asynchronously mirror to Teacher LLM if shadow evaluator registered
            if self.shadow_evaluator is not None:
                req_id = request_id_ctx.get()
                self.shadow_evaluator.shadow_async(req_id, text, prediction)
        else:
            teacher_pred: TriagePrediction | None = None
            if self.teacher.available:
                try:
                    teacher_pred = await self.teacher.predict(text)
                    cost = self.teacher.cost_per_call
                except (LLMError, CircuitBreakerOpenError) as exc:
                    logger.warning("Teacher LLM call failed or circuit breaker tripped: %s", exc)
                    reasons.append(f"teacher_failed:{type(exc).__name__}")
            else:
                reasons.append("teacher_unavailable_or_circuit_open")

            if teacher_pred is not None:
                prediction, route, model_name = teacher_pred, RouteTarget.TEACHER, self.teacher.name
            elif student_out is not None and self.student is not None:
                prediction, route, model_name, degraded = (student_out.prediction, RouteTarget.STUDENT,
                                                           self.student.name, True)
            else:
                prediction = self.heuristic.predict(text)
                route, model_name, degraded = RouteTarget.HEURISTIC, self.heuristic.name, True

        latency_ms = (time.perf_counter() - started) * 1000
        self.metrics.record(route, latency_ms, cost)

        # Record Prometheus routing decision metric
        ROUTER_INFERENCES_TOTAL.labels(route=route.value, intent=prediction.intent).inc()

        return RoutedResult(
            prediction=prediction, route=route, model_name=model_name, latency_ms=round(latency_ms, 3),
            student_latency_ms=round(student_out.latency_ms, 3) if student_out else None,
            ood_similarity=round(ood_sim, 4) if ood_sim is not None else None,
            reasons=reasons, degraded=degraded, estimated_cost_usd=cost,
        )


    def status(self) -> dict[str, Any]:
        return {
            "student_loaded": self.student is not None,
            "student_model": self.student.name if self.student else None,
            "prototypes_loaded": self.prototypes is not None,
            "teacher_available": self.teacher.available,
            "teacher_model": self.teacher.name,
            "thresholds": {"confidence": self.thresholds.confidence, "margin": self.thresholds.margin,
                           "ood_similarity": round(self.thresholds.ood_similarity, 4)},
            "in_process_metrics": self.metrics.snapshot(self._s.teacher_cost_per_call_usd),
        }


async def log_inference(conn: asyncpg.Connection, result: RoutedResult, ticket_id: UUID | None = None) -> None:
    """Persist routing telemetry for fleet-wide dashboards."""
    await conn.execute(
        """
        INSERT INTO inference_logs (ticket_id, route, model_name, intent, confidence, urgency,
                                    latency_ms, cost_usd, degraded, reasons)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        """,
        ticket_id, result.route.value, result.model_name, result.prediction.intent,
        result.prediction.confidence, result.prediction.urgency, result.latency_ms,
        result.estimated_cost_usd, result.degraded, result.reasons,
    )
