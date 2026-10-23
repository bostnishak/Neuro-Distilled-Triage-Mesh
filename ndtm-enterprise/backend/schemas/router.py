"""DistillMesh Semantic & Entropy Router request/response contract schemas."""
from __future__ import annotations

from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ExecutionTarget(str, Enum):
    SEMANTIC_CACHE = "SEMANTIC_CACHE"
    ONNX_STUDENT_INT8 = "ONNX_STUDENT_INT8"
    TEACHER_LLM_FALLBACK = "TEACHER_LLM_FALLBACK"


class RouterInferenceRequest(BaseModel):
    text: str = Field(..., min_length=5, max_length=10000, description="Incident text to categorize")


class RouterInferenceResponse(BaseModel):
    request_id: str
    intent: str
    confidence: float
    urgency: float
    execution_target: ExecutionTarget
    student_entropy: float | None = None
    ood_similarity: float | None = None
    latency_ms: float
    cost_saved_usd: float = 0.0
    from_cache: bool = False


class RetrainTriggerResponse(BaseModel):
    model_config = {"protected_namespaces": ()}

    status: str
    samples_curated_count: int
    training_started: bool
    model_version: str
    message: str


class ShadowDriftSampleItem(BaseModel):
    id: UUID
    request_id: str
    input_text: str
    student_output: dict[str, Any]
    teacher_output: dict[str, Any]
    kl_divergence: float
    used_for_retraining: bool
