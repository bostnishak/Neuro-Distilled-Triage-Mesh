import math
import numpy as np
from typing import Dict, List, Optional, Tuple
from core.config import settings
from core.logging_otel import logger


class PIDEntropyController:
    """Discrete Proportional-Integral-Derivative (PID) Controller for dynamic model routing."""

    def __init__(
        self,
        kp: float = 0.60,
        ki: float = 0.08,
        kd: float = 0.15,
        target_confidence: float = 0.88,
        min_threshold: float = 0.35,
        max_threshold: float = 0.75,
    ):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.target_confidence = target_confidence
        self.min_threshold = min_threshold
        self.max_threshold = max_threshold

        self.integral_error = 0.0
        self.prev_error = 0.0
        self.current_dynamic_threshold = settings.ROUTER_ENTROPY_THRESHOLD

    def update(self, observed_confidence: float, dt_seconds: float = 1.0) -> float:
        """Updates PID loop and returns adjusted entropy threshold u(t)."""
        error = self.target_confidence - observed_confidence

        # Accumulate integral with anti-windup clamping
        self.integral_error += error * dt_seconds
        self.integral_error = max(-2.0, min(2.0, self.integral_error))

        # Derivative
        derivative = (error - self.prev_error) / dt_seconds if dt_seconds > 0 else 0.0
        self.prev_error = error

        # Control output
        adjustment = (self.kp * error) + (self.ki * self.integral_error) + (self.kd * derivative)
        raw_threshold = settings.ROUTER_ENTROPY_THRESHOLD - adjustment
        self.current_dynamic_threshold = max(self.min_threshold, min(self.max_threshold, raw_threshold))

        return self.current_dynamic_threshold


class MahalanobisOODDetector:
    """Computes Mahalanobis distance DM(x) against empirical covariance of known incident distribution."""

    def __init__(self, dimension: int = 384):
        self.dimension = dimension
        self.mean_vector = np.zeros(dimension, dtype=np.float32)
        # Regularized diagonal covariance
        self.inv_covariance_diag = np.ones(dimension, dtype=np.float32)

    def calibrate(self, reference_embeddings: np.ndarray) -> None:
        """Calibrates mean and covariance from training in-distribution sample matrix (N, D)."""
        if reference_embeddings.shape[0] < 2:
            return
        self.mean_vector = np.mean(reference_embeddings, axis=0)
        variances = np.var(reference_embeddings, axis=0) + 1e-4  # Ridge regularization epsilon
        self.inv_covariance_diag = 1.0 / variances

    def compute_distance(self, embedding: np.ndarray) -> float:
        """Computes regularized Mahalanobis distance."""
        diff = embedding - self.mean_vector
        # DM^2 = sum_i (diff_i^2 / var_i)
        dist_sq = float(np.sum((diff * diff) * self.inv_covariance_diag))
        return math.sqrt(max(0.0, dist_sq))


class ModelRouter:
    """Unified Control-Theoretic & Entropy Routing Decision Engine."""

    def __init__(self):
        self.pid = PIDEntropyController()
        self.ood = MahalanobisOODDetector()

    @staticmethod
    def calculate_shannon_entropy(probs: np.ndarray) -> float:
        """Computes Shannon entropy H(p) = -sum p_i * log2(p_i)."""
        entropy = 0.0
        for p in probs:
            if p > 1e-9:
                entropy -= float(p * math.log2(p))
        return entropy

    def evaluate_route(
        self,
        probs: np.ndarray,
        embedding: np.ndarray,
        urgency: str,
    ) -> Tuple[str, float, float, float]:
        """Evaluates whether incident can be handled locally or requires Teacher LLM / HITL.

        Returns (route_decision, entropy, ood_dist, dynamic_threshold).
        route_decision in {"STUDENT_LOCAL", "TEACHER_ESCALATED", "HITL_REQUIRED"}.
        """
        confidence = float(np.max(probs))
        entropy = self.calculate_shannon_entropy(probs)
        dynamic_threshold = self.pid.update(confidence)
        ood_dist = self.ood.compute_distance(embedding)

        # High urgency with high entropy or severe OOD immediately demands human or teacher review
        if urgency == "CRITICAL" and (entropy > dynamic_threshold or ood_dist > 35.0):
            return "HITL_REQUIRED", entropy, ood_dist, dynamic_threshold

        if entropy > dynamic_threshold or ood_dist > 25.0:
            return "TEACHER_ESCALATED", entropy, ood_dist, dynamic_threshold

        return "STUDENT_LOCAL", entropy, ood_dist, dynamic_threshold
