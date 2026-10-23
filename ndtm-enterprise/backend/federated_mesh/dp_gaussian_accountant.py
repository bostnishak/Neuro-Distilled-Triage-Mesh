"""Differential Privacy Gaussian Mechanism & Privacy Budget Accountant.
Implements (epsilon, delta)-DP with strict L2 sensitivity clipping and
cumulative privacy expenditure tracking.
"""
from __future__ import annotations

import math
import numpy as np


class PrivacyBudgetExhaustedError(Exception):
    """Raised when the requested federated aggregation exceeds the cumulative epsilon budget."""
    pass


class GaussianDPAccountant:
    """Tracks privacy loss using the Gaussian Mechanism under (epsilon, delta)-DP."""

    def __init__(
        self,
        max_epsilon: float = 10.0,
        delta: float = 1e-5,
        clip_norm: float = 1.0,
        noise_multiplier: float = 1.2,
    ) -> None:
        self.max_epsilon = max_epsilon
        self.delta = delta
        self.clip_norm = clip_norm
        self.noise_multiplier = noise_multiplier
        self.cumulative_epsilon: float = 0.0

    def clip_gradient(self, vector: np.ndarray) -> np.ndarray:
        """Enforces ||g_tilde||_2 <= C_clip."""
        l2_norm = float(np.linalg.norm(vector))
        if l2_norm > self.clip_norm and l2_norm > 1e-9:
            return vector * (self.clip_norm / l2_norm)
        return vector

    def add_noise(self, vector: np.ndarray) -> np.ndarray:
        """Adds calibrated Gaussian noise N(0, (sigma * C_clip)^2 * I)."""
        scale = self.noise_multiplier * self.clip_norm
        noise = np.random.normal(0.0, scale, size=vector.shape).astype(vector.dtype)
        return vector + noise

    def spend_step(self) -> float:
        """Computes step privacy cost and updates total budget."""
        # Analytic Gaussian mechanism step cost
        step_eps = (math.sqrt(2.0 * math.log(1.25 / self.delta))) / max(self.noise_multiplier, 0.01)
        if self.cumulative_epsilon + step_eps > self.max_epsilon:
            raise PrivacyBudgetExhaustedError(
                f"Privacy budget exhausted: {self.cumulative_epsilon:.3f} + {step_eps:.3f} > {self.max_epsilon:.3f}"
            )
        self.cumulative_epsilon += step_eps
        return step_eps

    def reset_budget(self) -> None:
        self.cumulative_epsilon = 0.0
