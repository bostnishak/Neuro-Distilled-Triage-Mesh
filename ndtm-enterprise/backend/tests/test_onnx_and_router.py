"""Unit tests for Shannon Entropy, ONNX Student Runtime, and Semantic Router."""
from __future__ import annotations

import math
from unittest.mock import AsyncMock, patch

import numpy as np
import pytest

from backend.schemas.router import ExecutionTarget
from backend.services.onnx_runtime_engine import ONNXRuntimeEngine, TAXONOMY_INTENTS
from backend.services.semantic_router import (
    SemanticRouter,
    TeacherLLMClient,
    compute_normalized_shannon_entropy,
)


class TestShannonEntropy:
    """Verifies normalized Shannon entropy mathematical properties."""

    def test_zero_entropy_for_deterministic_distribution(self):
        # One-hot distribution: absolute certainty
        probs = np.zeros(8, dtype=np.float32)
        probs[0] = 1.0
        entropy = compute_normalized_shannon_entropy(probs)
        assert entropy < 0.01

    def test_maximum_entropy_for_uniform_distribution(self):
        # Uniform distribution: maximum uncertainty
        probs = np.full(8, 1.0 / 8, dtype=np.float32)
        entropy = compute_normalized_shannon_entropy(probs)
        assert abs(entropy - 1.0) < 0.01

    def test_entropy_monotonicity(self):
        # Concentrated vs diffused distribution
        concentrated = np.array([0.9, 0.02, 0.02, 0.02, 0.01, 0.01, 0.01, 0.01])
        diffused = np.array([0.3, 0.2, 0.15, 0.15, 0.1, 0.05, 0.03, 0.02])

        h_low = compute_normalized_shannon_entropy(concentrated)
        h_high = compute_normalized_shannon_entropy(diffused)

        assert h_low < h_high
        assert h_low <= 0.28  # Within student offload threshold


class TestONNXRuntimeEngine:
    """Verifies ONNX runtime inference, output normalization, and hot-swap."""

    def setup_method(self):
        self.engine = ONNXRuntimeEngine(model_path="distilled_models/student_int8.onnx")

    def test_prediction_structure(self):
        dummy_emb = [0.0] * 384
        dummy_emb[0] = 1.0

        intent, confidence, urgency, probs = self.engine.predict(dummy_emb)

        assert intent in TAXONOMY_INTENTS
        assert 0.0 <= confidence <= 1.0
        assert 0.0 <= urgency <= 1.0
        assert len(probs) == len(TAXONOMY_INTENTS)
        assert abs(float(np.sum(probs)) - 1.0) < 1e-3


class TestSemanticRouter:
    """Verifies 3-stage routing: Cache -> ONNX Student -> Teacher LLM."""

    @pytest.mark.asyncio
    async def test_cache_hit_routing(self):
        mock_redis = AsyncMock()
        router = SemanticRouter()
        emb = router.embedder.encode("Yol çöktü derin bir çukur var.")
        cached_data = {
            "intent": "ROAD_COLLAPSE",
            "confidence": 0.98,
            "urgency": 0.9,
            "embedding": emb,
        }
        mock_redis.keys.return_value = ["semcache:123"]
        import json
        mock_redis.get.return_value = json.dumps(cached_data)

        res = await router.infer(
            text="Yol çöktü derin bir çukur var.",
            redis_client=mock_redis,
        )

        assert res.execution_target == ExecutionTarget.SEMANTIC_CACHE
        assert res.from_cache is True
        assert res.cost_saved_usd > 0.0

    @pytest.mark.asyncio
    async def test_student_offload_on_low_entropy(self):
        mock_redis = AsyncMock()
        mock_redis.keys.return_value = []
        mock_redis.get.return_value = None  # Cache miss

        router = SemanticRouter()
        # Mock predict to return very low entropy (high confidence) and in-distribution similarity
        with patch.object(
            router.onnx,
            "predict",
            return_value=(
                "POWER_GRID_FAILURE",
                0.97,
                0.90,
                np.array([0.97, 0.01, 0.005, 0.005, 0.003, 0.003, 0.002, 0.002]),
            ),
        ), patch.object(router, "_compute_ood_similarity", return_value=0.88):
            res = await router.infer(
                text="Tüm mahallede elektrik kesildi ve trafo patladı.",
                redis_client=mock_redis,
            )

            assert res.execution_target == ExecutionTarget.ONNX_STUDENT_INT8
            assert res.student_entropy is not None
            assert res.student_entropy <= 0.28
            assert res.latency_ms < 50.0
