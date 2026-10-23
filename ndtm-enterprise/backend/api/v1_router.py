"""DistillMesh Semantic & Entropy Router REST endpoints."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user, get_db, get_redis, require_role
from backend.db.models import User
from backend.db.repositories import TelemetryRepository
from backend.schemas.auth import UserRole
from backend.schemas.router import (
    RetrainTriggerResponse,
    RouterInferenceRequest,
    RouterInferenceResponse,
    ShadowDriftSampleItem,
)
from backend.services.onnx_runtime_engine import ONNXRuntimeEngine
from backend.services.semantic_router import CalibratedSemanticRouter
from backend.services.shadow_evaluator import ShadowEvaluatorService
from backend.services.websocket_manager import ws_manager
from backend.workers.distillation_trainer import DistillationTrainerWorker

logger = logging.getLogger("api.router")
router = APIRouter(prefix="/router", tags=["DistillMesh Router"])

onnx_engine = ONNXRuntimeEngine()
shadow_evaluator = ShadowEvaluatorService()
trainer_worker = DistillationTrainerWorker(onnx_engine)


@router.post("/infer", response_model=RouterInferenceResponse)
async def infer_incident_intent(
    req: RouterInferenceRequest,
    session: AsyncSession = Depends(get_db),
    redis_client: aioredis.Redis | None = Depends(get_redis),
) -> RouterInferenceResponse:
    """Classifies incident with 3-stage routing: Semantic Cache -> INT8 Student -> Teacher LLM."""
    semantic_router = CalibratedSemanticRouter(
        onnx_engine=onnx_engine,
        redis_client=redis_client,
    )
    semantic_router.set_shadow_callback(shadow_evaluator.evaluate_async)

    result = await semantic_router.route_inference(req.text)

    # Log telemetry to database
    await TelemetryRepository.log_router_execution(
        session=session,
        request_id=result.request_id,
        execution_target=result.execution_target.value,
        student_entropy=result.student_entropy,
        ood_similarity=result.ood_similarity,
        latency_ms=result.latency_ms,
        cost_saved_usd=result.cost_saved_usd,
    )
    await session.commit()

    # Broadcast live router cockpit event
    await ws_manager.broadcast_event(
        "router_inference",
        {
            "request_id": result.request_id,
            "target": result.execution_target.value,
            "intent": result.intent,
            "latency_ms": result.latency_ms,
            "entropy": result.student_entropy,
            "cost_saved": result.cost_saved_usd,
        },
    )

    return result


@router.post("/retrain", response_model=RetrainTriggerResponse)
async def trigger_student_retraining(
    current_user: User = Depends(require_role([UserRole.ARCHITECT, UserRole.AUDITOR])),
) -> RetrainTriggerResponse:
    """Launches active learning knowledge distillation and in-memory INT8 model hot-swap."""
    logger.info("Active learning retraining initiated by user %s", current_user.email)
    asyncio.create_task(trainer_worker.run_distillation_cycle())

    return RetrainTriggerResponse(
        status="TRAINING_TRIGGERED",
        samples_curated_count=100,
        training_started=True,
        model_version=f"int8_hot_swap_v_{int(asyncio.get_event_loop().time())}",
        message="Active learning distillation cycle initiated in background. Real-time progress streaming via WebSocket.",
    )


@router.get("/drift-samples", response_model=list[ShadowDriftSampleItem])
async def list_shadow_drift_samples(
    limit: int = 50,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ShadowDriftSampleItem]:
    """Lists recent shadow divergence samples captured by background evaluator."""
    samples = await TelemetryRepository.get_unretrained_drift_samples(session, limit)
    return [
        ShadowDriftSampleItem(
            id=s.id,
            request_id=s.request_id,
            input_text=s.input_text,
            student_output=s.student_output,
            teacher_output=s.teacher_output,
            kl_divergence=s.kl_divergence,
            used_for_retraining=s.used_for_retraining,
        )
        for s in samples
    ]
