"""Module 2 Extension — Continuous Model Evaluation & Shadow Testing.

When the DistillMesh Semantic Router accepts a prediction from the fast
local ONNX student model (80% traffic path), this shadow testing service
asynchronously mirrors the request to the Teacher LLM in the background.

Metrics & Drift Tracking:
1. Intent agreement (`intent_match: bool`).
2. Urgency delta (`abs(student_urgency - teacher_urgency)`).
3. Semantic divergence score $[0.0, 1.0]$.
4. Persists comparison records to `shadow_evaluations` for automated drift monitoring.
5. Emits observations to Prometheus `SHADOW_DIVERGENCE_HISTOGRAM`.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import asyncpg

from core.llm import LLMClient
from middleware.telemetry_and_security import SHADOW_DIVERGENCE_HISTOGRAM
from services.router_service import TeacherClassifier, TriagePrediction

logger = logging.getLogger("shadow_testing")


def compute_divergence_score(student: TriagePrediction, teacher: TriagePrediction) -> tuple[bool, float, float]:
    """Calculate intent agreement, urgency delta, and normalized composite divergence score.

    Score range: 0.0 (perfect alignment) to 1.0 (complete disagreement).
    """
    intent_match = student.intent.strip().lower() == teacher.intent.strip().lower()
    urgency_delta = round(abs(student.urgency - teacher.urgency), 4)

    # Composite divergence score: 65% weight on intent mismatch, 35% on urgency delta
    intent_penalty = 0.0 if intent_match else 0.65
    urgency_penalty = min(urgency_delta, 1.0) * 0.35
    divergence_score = round(intent_penalty + urgency_penalty, 4)

    return intent_match, urgency_delta, divergence_score


class ShadowTestingEvaluator:
    """Non-blocking shadow tester evaluating student model against Teacher LLM."""

    def __init__(
        self,
        pool: asyncpg.Pool,
        teacher: TeacherClassifier,
        sample_rate: float = 1.0,  # 1.0 = evaluate all student requests; 0.1 = sample 10%
    ) -> None:
        self.pool = pool
        self.teacher = teacher
        self.sample_rate = sample_rate

    def shadow_async(
        self,
        request_id: str,
        input_text: str,
        student_pred: TriagePrediction,
    ) -> None:
        """Fire-and-forget background evaluation."""
        if not self.teacher.available:
            return

        # Fire background task without blocking the caller
        asyncio.create_task(
            self._evaluate(request_id, input_text, student_pred)
        )

    async def _evaluate(
        self,
        request_id: str,
        input_text: str,
        student_pred: TriagePrediction,
    ) -> None:
        started = time.perf_counter()
        try:
            # Query Teacher LLM
            teacher_pred = await self.teacher.predict(input_text)
            teacher_latency_ms = (time.perf_counter() - started) * 1000

            intent_match, urgency_delta, divergence_score = compute_divergence_score(
                student_pred, teacher_pred
            )

            # Observe in Prometheus
            SHADOW_DIVERGENCE_HISTOGRAM.observe(divergence_score)

            if divergence_score > 0.5:
                logger.warning(
                    "High model divergence detected on req %s! Student: %s (%.2f) vs Teacher: %s (%.2f) | Divergence: %.2f",
                    request_id,
                    student_pred.intent, student_pred.urgency,
                    teacher_pred.intent, teacher_pred.urgency,
                    divergence_score,
                )

            # Store in database
            async with self.pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO shadow_evaluations (
                        request_id, input_text, student_intent, teacher_intent,
                        student_confidence, teacher_confidence, student_urgency,
                        teacher_urgency, intent_match, urgency_delta,
                        divergence_score, teacher_latency_ms
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                    """,
                    request_id,
                    input_text[:2000],
                    student_pred.intent,
                    teacher_pred.intent,
                    student_pred.confidence,
                    teacher_pred.confidence,
                    student_pred.urgency,
                    teacher_pred.urgency,
                    intent_match,
                    urgency_delta,
                    divergence_score,
                    teacher_latency_ms,
                )

        except Exception as exc:
            # Shadow evaluations should never bubble errors to user threads
            logger.warning("Shadow evaluation failed on req %s: %s", request_id, exc)
