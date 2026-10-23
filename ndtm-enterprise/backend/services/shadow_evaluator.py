"""Shadow evaluation and Jensen-Shannon drift monitoring for continuous model distillation."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import numpy as np

from backend.db.repositories import TelemetryRepository
from backend.db.session import async_session_factory
from backend.services.semantic_router import TeacherLLMClient

logger = logging.getLogger("services.shadow_evaluator")


def compute_kl_divergence(p: np.ndarray, q: np.ndarray) -> float:
    """Computes Kullback-Leibler divergence D_KL(P || Q)."""
    eps = 1e-12
    p_safe = np.clip(p, eps, 1.0)
    q_safe = np.clip(q, eps, 1.0)
    # Re-normalize
    p_safe = p_safe / np.sum(p_safe)
    q_safe = q_safe / np.sum(q_safe)
    return float(np.sum(p_safe * np.log(p_safe / q_safe)))


def compute_jensen_shannon_divergence(p: np.ndarray, q: np.ndarray) -> float:
    """Computes symmetric, bounded Jensen-Shannon Divergence in [0.0, 1.0]."""
    m = 0.5 * (p + q)
    js = 0.5 * compute_kl_divergence(p, m) + 0.5 * compute_kl_divergence(q, m)
    return round(float(np.clip(js, 0.0, 1.0)), 4)


class ShadowEvaluatorService:
    def __init__(self, teacher_client: TeacherLLMClient | None = None) -> None:
        self.teacher = teacher_client or TeacherLLMClient()

    async def evaluate_async(
        self,
        request_id: str,
        input_text: str,
        student_intent: str,
        student_confidence: float,
        student_probs: np.ndarray,
    ) -> None:
        """Asynchronously invokes Teacher LLM, evaluates divergence, and stores drift samples."""
        try:
            teacher_res = await self.teacher.predict_teacher(input_text)
            teacher_intent = teacher_res["intent"]
            teacher_conf = teacher_res["confidence"]

            # Construct synthetic teacher distribution
            k = len(student_probs)
            teacher_probs = np.full(k, (1.0 - teacher_conf) / (k - 1), dtype=np.float32)
            # Find index matching intent or default to 0
            teacher_probs[0] = teacher_conf
            teacher_probs = teacher_probs / np.sum(teacher_probs)

            js_div = compute_jensen_shannon_divergence(student_probs, teacher_probs)

            # Check if intent mismatched or divergence high
            if student_intent != teacher_intent or js_div > 0.35:
                logger.warning(
                    "High model drift detected on req %s! Student: %s (%.2f) vs Teacher: %s (%.2f) | JS-Div: %.4f",
                    request_id,
                    student_intent,
                    student_confidence,
                    teacher_intent,
                    teacher_conf,
                    js_div,
                )

                # Persist to database
                async with async_session_factory() as session:
                    async with session.begin():
                        await TelemetryRepository.save_shadow_sample(
                            session=session,
                            request_id=request_id,
                            input_text=input_text,
                            student_output={"intent": student_intent, "confidence": student_confidence},
                            teacher_output=teacher_res,
                            kl_divergence=js_div,
                        )

        except Exception as exc:
            logger.debug("Shadow evaluation background task error: %s", exc)
