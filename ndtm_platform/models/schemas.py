"""Pydantic v2 domain models and API contract schemas for NDTM."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


# =============================================================================
# Enums
# =============================================================================
class TicketStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    RESOLVED = "resolved"
    ESCALATED = "escalated"


class ExecutionPath(str, Enum):
    ONNX_STUDENT = "onnx_student"
    TEACHER_LLM = "teacher_llm"
    SEMANTIC_CACHE = "semantic_cache"
    HEURISTIC = "heuristic"


class Skill(str, Enum):
    ELECTRICAL = "electrical"
    PLUMBING = "plumbing"
    PAVEMENT = "pavement"
    CIVIL = "civil"
    NETWORKING = "networking"
    HAZMAT = "hazmat"
    GENERAL = "general"


# =============================================================================
# Triage & Deduplication Schemas
# =============================================================================
class TriageReportRequest(BaseModel):
    description: str = Field(..., min_length=10, max_length=10000, description="Citizen/incident report text")
    user_id: UUID | None = None
    category: str | None = None
    image_url: str | None = None


class TriageOutcome(BaseModel):
    status: str = Field(..., description="created | merged_duplicate | clarification_required")
    message: str
    ticket_id: UUID | None = None
    similarity: float | None = None
    cleaned_description: str | None = None
    urgency_score: float | None = None
    category: str | None = None


# =============================================================================
# Semantic Router & Inference Schemas
# =============================================================================
class InferenceRequest(BaseModel):
    text: str = Field(..., min_length=5, max_length=10000)


class InferenceResponse(BaseModel):
    intent: str
    confidence: float
    urgency: float
    execution_path: ExecutionPath
    latency_ms: float
    cost_usd: float
    from_cache: bool = False
    entities: list[dict[str, Any]] = Field(default_factory=list)


# =============================================================================
# Neuro-Symbolic Verification Schemas
# =============================================================================
class Technician(BaseModel):
    id: str
    name: str
    skills: list[Skill]
    shift_hours: float = Field(8.0, ge=1.0, le=14.0)
    max_tasks: int = Field(5, ge=1)


class ScheduledTask(BaseModel):
    id: str
    title: str
    priority: int = Field(ge=1, le=4)
    required_skill: Skill
    estimated_duration_hours: float = Field(ge=0.5, le=8.0)
    deadline_hours: float = Field(8.0, ge=0.5, le=24.0)
    location: str


class TaskAssignment(BaseModel):
    task_id: str
    technician_id: str
    start_hour: float
    end_hour: float


class SchedulePlan(BaseModel):
    assignments: list[TaskAssignment]
    rationale: str = ""


class SymbolicVerificationResponse(BaseModel):
    is_valid: bool
    status: str  # verified | repaired | solved_optimal | unsat
    plan: SchedulePlan | None = None
    violations: list[dict[str, Any]] = Field(default_factory=list)
    solver_time_ms: float
    rounds_executed: int = 0


# =============================================================================
# Multi-Agent Workflow Schemas
# =============================================================================
class MultiAgentWorkflowRequest(BaseModel):
    ticket_id: UUID | None = None
    description: str
    category: str | None = None


class MultiAgentWorkflowResponse(BaseModel):
    ticket_id: UUID | None = None
    consensus_reached: bool
    consensus_score: float
    triage_summary: dict[str, Any]
    compliance_audit: dict[str, Any]
    execution_plan: dict[str, Any]
    hitl_required: bool
    review_task_id: UUID | None = None


# =============================================================================
# Continuous Learning Schemas
# =============================================================================
class ActiveLearningTriggerResponse(BaseModel):
    status: str
    unprocessed_candidates_count: int
    training_started: bool
    message: str
