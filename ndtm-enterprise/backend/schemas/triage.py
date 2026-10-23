"""Multimodal triage and deduplication request/response contract schemas."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class TicketStatus(str, Enum):
    REJECTED_QUALITY = "REJECTED_QUALITY"
    DEDUPLICATED = "DEDUPLICATED"
    QUEUED = "QUEUED"
    TRIAGED = "TRIAGED"
    SCHEDULED = "SCHEDULED"
    DLQ_FAILED = "DLQ_FAILED"


class IncidentSubmissionRequest(BaseModel):
    description: str = Field(..., min_length=10, max_length=10000, description="Raw incident report")
    category: str = Field(default="GENERAL", max_length=64)
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    urgency_score: int = Field(default=5, ge=1, le=10)
    image_base64: str | None = Field(default=None, description="Optional Base64 encoded JPEG/PNG image")


class IncidentSubmissionResponse(BaseModel):
    incident_id: UUID
    status: TicketStatus
    is_duplicate: bool
    parent_incident_id: UUID | None = None
    duplicate_count: int = 1
    scrubbed_text: str
    laplacian_score: float | None = None
    distance_meters: float | None = None
    cosine_similarity: float | None = None
    message: str


class QualityGateRejectionResponse(BaseModel):
    requires_clarification: bool = True
    reason: str
    laplacian_score: float
    clarification_prompt: str


class IncidentDetailResponse(BaseModel):
    id: UUID
    reporter_id: UUID | None
    parent_incident_id: UUID | None
    duplicate_count: int
    scrubbed_text: str
    category: str
    urgency_score: int
    status: TicketStatus
    latitude: float
    longitude: float
    image_laplacian_score: float | None
    created_at: datetime
    updated_at: datetime
