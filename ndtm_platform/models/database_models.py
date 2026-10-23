"""Database entity record representations matching schema.sql."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID


@dataclass(slots=True)
class UserRecord:
    id: UUID
    email: str
    hashed_password: str
    created_at: datetime


@dataclass(slots=True)
class TicketRecord:
    id: UUID
    user_id: UUID | None
    raw_description: str
    cleaned_description: str
    image_url: str | None
    category: str | None
    urgency_score: float | None
    status: str
    report_count: int
    created_at: datetime


@dataclass(slots=True)
class TicketEmbeddingRecord:
    id: int
    ticket_id: UUID
    embedding: list[float]
    metadata: dict[str, Any]
    created_at: datetime


@dataclass(slots=True)
class AuditLogRecord:
    id: int
    request_id: str
    endpoint: str
    latency_ms: float
    token_counts: int
    execution_path: str
    cost_usd: Decimal
    created_at: datetime


@dataclass(slots=True)
class FineTuningCandidateRecord:
    id: int
    input_prompt: str
    student_output: dict[str, Any]
    teacher_output: dict[str, Any]
    divergence_score: float
    processed: bool
    created_at: datetime


@dataclass(slots=True)
class IdempotencyRecord:
    key: str
    response_payload: dict[str, Any]
    created_at: datetime


@dataclass(slots=True)
class HITLReviewTaskRecord:
    id: UUID
    ticket_id: UUID | None
    agent_name: str
    consensus_score: float
    workflow_state: dict[str, Any]
    assigned_reviewer: str | None
    resolution_notes: str | None
    status: str
    created_at: datetime
    resolved_at: datetime | None
