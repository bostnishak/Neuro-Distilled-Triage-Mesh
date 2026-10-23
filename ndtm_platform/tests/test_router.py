"""Unit tests for Semantic KV-Cache, Router, and Circuit Breaker."""
from __future__ import annotations

import asyncio
import pytest

from ndtm_platform.cache.semantic_cache import DistributedSemanticKVCache
from ndtm_platform.middleware.circuit_breaker import CircuitBreaker, CircuitBreakerOpenException
from ndtm_platform.services.router_service import ONNXStudentRunner


@pytest.mark.asyncio
async def test_semantic_kv_cache_hit_and_miss():
    cache = DistributedSemanticKVCache(redis_client=None, similarity_threshold=0.95)

    base_emb = [0.1] * 768
    await cache.put(
        prompt_prefix="Cadde üzerinde su borusu patladı",
        embedding=base_emb,
        intent="water_leak",
        confidence=0.98,
        urgency=0.85,
    )

    # 1. Query with 100% identical embedding -> HIT
    entry, sim = await cache.lookup(base_emb)
    assert entry is not None
    assert sim >= 0.99
    assert entry.intent == "water_leak"

    # 2. Query with slight perturbation (cosine sim > 0.95) -> HIT
    perturbed_emb = [0.1005] * 768
    entry, sim = await cache.lookup(perturbed_emb)
    assert entry is not None
    assert sim > 0.95
    assert entry.intent == "water_leak"

    # 3. Query with orthogonal embedding -> MISS
    orthogonal_emb = [1.0 if i == 0 else 0.0 for i in range(768)]
    entry, sim = await cache.lookup(orthogonal_emb)
    assert entry is None
    assert sim < 0.95


@pytest.mark.asyncio
async def test_circuit_breaker_tripping():
    cb = CircuitBreaker(failure_threshold=2, recovery_time=1.0)

    async def faulty_teacher():
        raise RuntimeError("Teacher LLM 503 Service Unavailable")

    # First failure
    with pytest.raises(RuntimeError):
        await cb.call(faulty_teacher)
    assert cb.state.value == "closed"

    # Second failure -> Trips breaker to OPEN
    with pytest.raises(RuntimeError):
        await cb.call(faulty_teacher)
    assert cb.state.value == "open"

    # Subsequent call immediately rejected with CircuitBreakerOpenException
    with pytest.raises(CircuitBreakerOpenException):
        await cb.call(faulty_teacher)


def test_onnx_student_runner_inference():
    runner = ONNXStudentRunner(model_path=None)
    dummy_emb = [0.05] * 768
    intent, conf, urgency = runner.predict(dummy_emb)

    assert isinstance(intent, str)
    assert conf > 0.0
    assert 0.0 <= urgency <= 1.0
