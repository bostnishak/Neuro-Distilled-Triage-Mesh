"""Module: Shadow Testing & Divergence Evaluator.

Asynchronously compares the ONNX student predictions against the Teacher LLM in the background.
If the semantic divergence score is high (> 0.40), automatically logs the candidate
into PostgreSQL `fine_tuning_candidates` and checks if retraining should be triggered.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

import asyncpg

from ndtm_platform.middleware.telemetry import REGISTRY
from ndtm_platform.services.router_service import TeacherLLMClient

logger = logging.getLogger("shadow_testing")


def compute_divergence(
    student_intent: str,
    student_urgency: float,
    teacher_intent: str,
    teacher_urgency: float,
) -> tuple[bool, float, float]:
    """Calculates intent match boolean, urgency delta, and composite divergence score [0.0, 1.0]."""
    intent_match = student_intent.strip().lower() == teacher_intent.strip().lower()
    urgency_delta = round(abs(student_urgency - teacher_urgency), 4)

    # Composite divergence formula: 65% weight on intent mismatch, 35% on urgency delta
    intent_penalty = 0.0 if intent_match else 0.65
    urgency_penalty = min(urgency_delta, 1.0) * 0.35
    divergence_score = round(intent_penalty + urgency_penalty, 4)

    return intent_match, urgency_delta, divergence_score


class ShadowTestingEvaluator:
    """Non-blocking shadow tester evaluating student vs teacher outputs."""

    def __init__(
        self,
        pool: asyncpg.Pool,
        teacher: TeacherLLMClient | None = None,
        divergence_threshold: float = 0.40,
        retraining_trigger_callback: Any = None,
    ) -> None:
        self.pool = pool
        self.teacher = teacher or TeacherLLMClient()
        self.divergence_threshold = divergence_threshold
        self.retraining_trigger_callback = retraining_trigger_callback

    def shadow_async(
        self,
        request_id: str,
        input_text: str,
        student_intent: str,
        student_conf: float,
        student_urgency: float,
    ) -> None:
        """Schedules fire-and-forget background evaluation without blocking the user response."""
        asyncio.create_task(
            self._evaluate(request_id, input_text, student_intent, student_conf, student_urgency)
        )

    async def _evaluate(
        self,
        request_id: str,
        input_text: str,
        student_intent: str,
        student_conf: float,
        student_urgency: float,
    ) -> None:
        try:
            teacher_res = await self.teacher.generate_triage(input_text)
            teacher_intent = teacher_res["intent"]
            teacher_conf = teacher_res["confidence"]
            teacher_urgency = teacher_res["urgency"]

            intent_match, urgency_delta, divergence_score = compute_divergence(
                student_intent, student_urgency, teacher_intent, teacher_urgency
            )

            # Record in Prometheus
            REGISTRY.shadow_divergence.observe(divergence_score)

            if divergence_score >= self.divergence_threshold:
                logger.warning(
                    "High model divergence (%.3f >= %.2f) on req %s! Student: %s (%.2f) vs Teacher: %s (%.2f)",
                    divergence_score,
                    self.divergence_threshold,
                    request_id,
                    student_intent,
                    student_urgency,
                    teacher_intent,
                    teacher_urgency,
                )

                # Persist high-divergence sample to fine_tuning_candidates table
                student_out = {
                    "intent": student_intent,
                    "confidence": student_conf,
                    "urgency": student_urgency,
                }
                teacher_out = {
                    "intent": teacher_intent,
                    "confidence": teacher_conf,
                    "urgency": teacher_urgency,
                }

                async with self.pool.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO fine_tuning_candidates (
                            input_prompt, student_output, teacher_output, divergence_score, processed
                        ) VALUES ($1, $2::jsonb, $3::jsonb, $4, false);
                        """,
                        input_text,
                        json.dumps(student_out),
                        json.dumps(teacher_out),
                        divergence_score,
                    )

                    # Check current total unprocessed candidates
                    count = await conn.fetchval(
                        "SELECT COUNT(*) FROM fine_tuning_candidates WHERE processed = false;"
                    )

                logger.info("Current unprocessed fine-tuning candidates count: %d", count)

                # If threshold callback provided and count reached threshold, trigger retraining
                if self.retraining_trigger_callback is not None:
                    await self.retraining_trigger_callback(count)

        except Exception as exc:
            # Shadow evaluation must never crash application threads
            logger.debug("Shadow evaluation exception on req %s: %s", request_id, exc)
