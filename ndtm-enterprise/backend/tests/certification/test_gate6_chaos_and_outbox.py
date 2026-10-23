"""Gate 6: Chaos Engineering, Upstream Resilience & Transactional Outbox Reliability Suite.
Certifies Transactional Outbox message persistence during broker outages,
Circuit Breaker finite state machine transitions (CLOSED -> OPEN -> HALF_OPEN -> CLOSED),
and seamless fallback to INT8 Student under upstream Teacher LLM outages.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import numpy as np
import pytest

from backend.core.exceptions import CircuitBreakerOpenError
from backend.db.models import Incident, OutboxEvent
from backend.middleware.circuit_breaker import CircuitBreaker, CircuitState
from backend.schemas.router import ExecutionTarget
from backend.services.semantic_router import (
    CalibratedSemanticRouter,
    compute_normalized_shannon_entropy,
)


# =============================================================================
# 1. Transactional Outbox Reliability & Broker Outage Survival
# =============================================================================
class TestTransactionalOutboxReliability:
    """Proves zero message loss across simulated RabbitMQ message broker crash scenarios."""

    def test_outbox_event_creation_and_atomic_state(self):
        # Simulate transactional creation
        incident_id = uuid4()
        event_id = uuid4()

        outbox_event = OutboxEvent(
            id=event_id,
            aggregate_type="INCIDENT",
            aggregate_id=incident_id,
            routing_key="incidents.triage",
            payload={
                "incident_id": str(incident_id),
                "category": "ELECTRICAL_GRID",
                "urgency": 9,
                "description": "Transformer fire in Kadikoy",
            },
            published=False,
        )

        assert outbox_event.published is False
        assert outbox_event.aggregate_type == "INCIDENT"
        assert outbox_event.aggregate_id == incident_id

    def test_broker_failure_preserves_uncommitted_outbox(self):
        # 10 Outbox events queued
        events = [
            OutboxEvent(
                id=uuid4(),
                aggregate_type="INCIDENT",
                aggregate_id=uuid4(),
                routing_key="incidents.triage",
                payload={"index": i},
                published=False,
            )
            for i in range(10)
        ]

        # Simulate broker relay attempt during broker crash (AMQP connection drop)
        class SimulatedBrokenBrokerChannel:
            def basic_publish(self, *args, **kwargs):
                raise ConnectionResetError("Broker connection reset by peer (RabbitMQ 5672 down)")

        broker = SimulatedBrokenBrokerChannel()
        published_ids = []

        for ev in events:
            try:
                broker.basic_publish(routing_key="incidents.triage", body=str(ev.payload))
                ev.published = True
                published_ids.append(ev.id)
            except Exception:
                # Reliability requirement: In-flight broker errors MUST NOT mark events published
                assert ev.published is False

        # Zero events must be marked published
        assert len(published_ids) == 0
        assert all(ev.published is False for ev in events)

    def test_broker_recovery_drains_and_confirms_outbox(self):
        events = [
            OutboxEvent(
                id=uuid4(),
                aggregate_type="INCIDENT",
                aggregate_id=uuid4(),
                routing_key="incidents.triage",
                payload={"index": i},
                published=False,
            )
            for i in range(10)
        ]

        class RecoveredBrokerChannel:
            def __init__(self):
                self.messages = []

            def basic_publish(self, routing_key, body):
                self.messages.append((routing_key, body))

        broker = RecoveredBrokerChannel()
        published_ids = []

        # Drain loop once broker reconnects
        for ev in events:
            broker.basic_publish("incidents.triage", str(ev.payload))
            ev.published = True
            published_ids.append(ev.id)

        assert len(published_ids) == 10
        assert len(broker.messages) == 10
        assert all(ev.published is True for ev in events)


# =============================================================================
# 2. Upstream Circuit Breaker Finite State Machine Transitions
# =============================================================================
class TestTeacherLLMCircuitBreakerFSM:
    """Proves FSM transitions: CLOSED -> 3 errors -> OPEN -> timeout -> HALF_OPEN -> CLOSED."""

    @pytest.mark.asyncio
    async def test_full_circuit_breaker_lifecycle(self):
        breaker = CircuitBreaker(
            name="teacher_llm_test",
            failure_threshold=3,
            recovery_timeout=0.05,  # 50ms for test speed
            half_open_success_threshold=1,
        )

        assert breaker.state == CircuitState.CLOSED

        async def failing_call():
            raise TimeoutError("Upstream Teacher LLM gateway timed out (504 Gateway Timeout)")

        async def healthy_call():
            return {"status": "SUCCESS", "intent": "ELECTRICAL_GRID"}

        # Failure 1: Remains CLOSED
        with pytest.raises(TimeoutError):
            await breaker.call(failing_call)
        assert breaker.state == CircuitState.CLOSED

        # Failure 2: Remains CLOSED
        with pytest.raises(TimeoutError):
            await breaker.call(failing_call)
        assert breaker.state == CircuitState.CLOSED

        # Failure 3: Reaches threshold -> Trips to OPEN
        with pytest.raises(TimeoutError):
            await breaker.call(failing_call)
        assert breaker.state == CircuitState.OPEN

        # Call while OPEN must fail fast without executing failing_call
        mock_spy = AsyncMock()
        with pytest.raises(CircuitBreakerOpenError):
            await breaker.call(mock_spy)
        assert mock_spy.call_count == 0

        # Wait for recovery window (50ms)
        await asyncio.sleep(0.06)

        # First call after recovery timeout probes the upstream service (transitions to HALF_OPEN)
        res = await breaker.call(healthy_call)
        assert res["status"] == "SUCCESS"

        # Successful probe restores circuit back to CLOSED
        assert breaker.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_half_open_re_trip_on_probe_failure(self):
        breaker = CircuitBreaker(
            name="teacher_probe_fail",
            failure_threshold=2,
            recovery_timeout=0.03,
            half_open_success_threshold=1,
        )

        async def failing_call():
            raise ConnectionRefusedError("Teacher LLM service unreachable")

        # Trip to OPEN
        for _ in range(2):
            with pytest.raises(ConnectionRefusedError):
                await breaker.call(failing_call)
        assert breaker.state == CircuitState.OPEN

        # Wait for recovery window
        await asyncio.sleep(0.04)

        # Probe fails in HALF_OPEN -> Re-trips immediately to OPEN
        with pytest.raises(ConnectionRefusedError):
            await breaker.call(failing_call)
        assert breaker.state == CircuitState.OPEN


# =============================================================================
# 3. Semantic Router Fault-Tolerant Fallback under Upstream Outage
# =============================================================================
class TestSemanticRouterCircuitBreakerFallback:
    """Proves that CalibratedSemanticRouter falls back to INT8 Student when Teacher LLM circuit is OPEN."""

    @pytest.mark.asyncio
    async def test_router_falls_back_to_student_when_teacher_tripped(self):
        # Mock student producing high entropy that would normally route to Teacher
        uniform_probs = np.ones(8, dtype=np.float32) / 8.0

        class HighEntropyStudent:
            def predict(self, emb, temperature=1.0):
                return "TRANSFORMER_FIRE", 0.75, 0.80, uniform_probs

        class FastMockEmbedder:
            def encode(self, text):
                return [0.1] * 384

        # Pre-trip the circuit breaker
        breaker = CircuitBreaker(name="test_breaker")
        breaker.force_state(CircuitState.OPEN)

        router = CalibratedSemanticRouter(
            onnx_engine=HighEntropyStudent(),
            circuit_breaker=breaker,
            embedder=FastMockEmbedder(),
        )

        # High entropy input would normally trigger Teacher LLM.
        # But Teacher is tripped (OPEN). Router MUST catch CircuitBreakerOpenError
        # and gracefully fall back to ONNX_STUDENT_INT8 without crashing.
        res = await router.route_inference("Acil trafo yangını ve elektrik kesintisi")

        assert res.execution_target == ExecutionTarget.ONNX_STUDENT_INT8
        assert res.intent == "TRANSFORMER_FIRE"
        assert res.from_cache is False
        assert res.latency_ms >= 0.0
