import math
import numpy as np
from typing import Dict, Any, Tuple, Optional
from core.config import settings
from core.exceptions import SpeculativeRejectionException
from core.logging_otel import logger


class SpeculativeDraftVerifier:
    """Verifies speculative inferences emitted by student model against high-capacity teacher distribution."""

    def __init__(self, rejection_threshold: Optional[float] = None):
        self.rejection_threshold = rejection_threshold or settings.SPECULATIVE_REJECTION_THRESHOLD

    @staticmethod
    def jensen_shannon_divergence(p: np.ndarray, q: np.ndarray) -> float:
        """Computes symmetric Jensen-Shannon divergence JSD(P || Q) in [0, 1]."""
        p = np.clip(p, 1e-12, 1.0)
        q = np.clip(q, 1e-12, 1.0)
        p = p / np.sum(p)
        q = q / np.sum(q)
        m = 0.5 * (p + q)

        kl_pm = np.sum(p * np.log2(p / m))
        kl_qm = np.sum(q * np.log2(q / m))
        jsd = 0.5 * (kl_pm + kl_qm)
        return float(np.sqrt(max(0.0, jsd)))

    def verify_draft(
        self,
        draft_id: str,
        student_category: str,
        student_probs: np.ndarray,
        teacher_category: str,
        teacher_probs: np.ndarray,
    ) -> Tuple[bool, float, float]:
        """Validates student draft against teacher probability distribution.

        Returns (is_accepted, acceptance_ratio, divergence_score).
        Raises SpeculativeRejectionException if divergence exceeds threshold.
        """
        jsd = self.jensen_shannon_divergence(student_probs, teacher_probs)

        # Acceptance probability ratio for the proposed class
        # Look up index
        pred_idx = int(np.argmax(student_probs))
        p_student = float(student_probs[pred_idx])
        p_teacher = float(teacher_probs[pred_idx]) if pred_idx < len(teacher_probs) else 0.0

        acceptance_ratio = min(1.0, (p_teacher / p_student) if p_student > 0 else 0.0)

        # Acceptance condition: categories match or JSD <= (1 - rejection_threshold)
        is_accepted = (student_category == teacher_category) and (acceptance_ratio >= (1.0 - self.rejection_threshold))

        if not is_accepted:
            logger.warning(
                "speculative_draft_rejected",
                draft_id=draft_id,
                student_cat=student_category,
                teacher_cat=teacher_category,
                jsd=jsd,
                acceptance_ratio=acceptance_ratio,
            )
            raise SpeculativeRejectionException(draft_id, acceptance_ratio, 1.0 - self.rejection_threshold)

        return True, acceptance_ratio, jsd
