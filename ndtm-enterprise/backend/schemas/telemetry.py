"""System health, metrics cockpit, and SRE chaos schemas."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ServiceHealthItem(BaseModel):
    status: str  # connected | degraded | offline | ready
    latency_ms: float | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class SystemHealthResponse(BaseModel):
    status: str  # healthy | degraded | unhealthy
    environment: str
    timestamp: float
    services: dict[str, ServiceHealthItem]


class LiveMetricsSnapshot(BaseModel):
    total_requests: int
    onnx_offload_ratio: float
    avg_latency_ms: float
    cumulative_cost_saved_usd: float
    circuit_breaker_state: str  # CLOSED | OPEN | HALF_OPEN
    queue_depth_triage: int
    queue_depth_shadow: int
    queue_depth_dlq: int


class ChaosSimulationRequest(BaseModel):
    scenario: str = Field(
        ...,
        description="TEACHER_503_OUTAGE | INJECT_BLURRY_IMAGE | PROMPT_INJECTION_ATTACK | REDIS_LATENCY_SPIKE",
    )
    intensity: float = Field(default=1.0, ge=0.1, le=5.0)


class ChaosSimulationResponse(BaseModel):
    scenario: str
    action_taken: str
    circuit_breaker_tripped: bool = False
    firewall_blocked: bool = False
    affected_subsystem: str
    timestamp: float


class DLQMessageItem(BaseModel):
    id: UUID
    routing_key: str
    payload: dict[str, Any]
    retry_count: int
    error_reason: str
    created_at: str
