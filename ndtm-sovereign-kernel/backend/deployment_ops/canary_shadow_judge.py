"""
Neuro-Distilled Triage Mesh (NDTM) — Sovereign Distributed & Failure-Proof Kernel
RFC-NDTM-OMEGA: Production Hardening Engine v3.0

Phase 33: Canary Shadow Judge
Automated Canary Rollout Evaluator using Two-Sample Kolmogorov-Smirnov Test (D_KS)
and Automated Rollback Protection.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


class CanaryVerdict(str, Enum):
    CANARY_HEALTHY_PROCEED = "CANARY_HEALTHY_PROCEED"
    CANARY_MARGINAL_MONITOR = "CANARY_MARGINAL_MONITOR"
    CANARY_DEGRADED_ROLLBACK = "CANARY_DEGRADED_ROLLBACK"


@dataclass
class CanaryEvaluationReport:
    step_name: str
    traffic_weight_percent: float
    sample_size_baseline: int
    sample_size_canary: int
    ks_statistic: float
    ks_critical_value: float
    p_value: float
    baseline_error_rate: float
    canary_error_rate: float
    error_rate_delta: float
    verdict: CanaryVerdict
    rollback_triggered: bool
    reason: str


class CanaryShadowJudge:
    """
    Argo Rollouts Metric Webhook & Canary Guard.
    
    Performs Two-Sample Kolmogorov-Smirnov testing between Baseline model outputs
    and Canary shadow candidate model outputs to detect subtle distributional shifts,
    hallucination drifts, or latency anomalies before promoting traffic.
    """

    def __init__(
        self,
        significance_alpha: float = 0.01,
        max_error_rate_delta: float = 0.015,  # Max 1.5% increase in error rate allowed
        critical_ks_ceiling: float = 0.12,    # Hard limit on CDF divergence
    ):
        self.alpha = significance_alpha
        self.max_err_delta = max_error_rate_delta
        self.ks_ceiling = critical_ks_ceiling

    @staticmethod
    def _compute_two_sample_ks(sample1: np.ndarray, sample2: np.ndarray) -> Tuple[float, float]:
        """
        Computes the Kolmogorov-Smirnov statistic D = sup_x |F1(x) - F2(x)|
        and asymptotic p-value in pure numpy.
        """
        n1 = len(sample1)
        n2 = len(sample2)
        if n1 == 0 or n2 == 0:
            return 0.0, 1.0

        # Concatenate and sort all unique evaluation points
        data1 = np.sort(sample1)
        data2 = np.sort(sample2)

        data_all = np.concatenate([data1, data2])
        # Empirical CDFs evaluated at all combined points
        cdf1 = np.searchsorted(data1, data_all, side="right") / float(n1)
        cdf2 = np.searchsorted(data2, data_all, side="right") / float(n2)

        d_stat = float(np.max(np.abs(cdf1 - cdf2)))

        # Asymptotic p-value approximation
        en = math.sqrt((n1 * n2) / float(n1 + n2))
        lambda_val = (en + 0.12 + 0.11 / en) * d_stat

        # Kolmogorov distribution survival function sum
        p_val = 0.0
        for j in range(1, 101):
            term = 2.0 * ((-1) ** (j - 1)) * math.exp(-2.0 * (j ** 2) * (lambda_val ** 2))
            p_val += term
            if abs(term) < 1e-8:
                break
        p_val = max(0.0, min(1.0, p_val))

        return d_stat, p_val

    def evaluate_canary_step(
        self,
        step_name: str,
        traffic_weight_percent: float,
        baseline_outputs: np.ndarray,
        canary_outputs: np.ndarray,
        baseline_errors_count: int,
        canary_errors_count: int,
    ) -> CanaryEvaluationReport:
        """
        Evaluates whether a canary step can safely advance to the next traffic weight.
        """
        s_base = np.asarray(baseline_outputs, dtype=np.float64).flatten()
        s_canary = np.asarray(canary_outputs, dtype=np.float64).flatten()

        n1 = len(s_base)
        n2 = len(s_canary)

        if n1 < 10 or n2 < 10:
            return CanaryEvaluationReport(
                step_name=step_name,
                traffic_weight_percent=traffic_weight_percent,
                sample_size_baseline=n1,
                sample_size_canary=n2,
                ks_statistic=0.0,
                ks_critical_value=0.5,
                p_value=1.0,
                baseline_error_rate=0.0,
                canary_error_rate=0.0,
                error_rate_delta=0.0,
                verdict=CanaryVerdict.CANARY_MARGINAL_MONITOR,
                rollback_triggered=False,
                reason="Insufficient sample count to evaluate statistical significance.",
            )

        # 1. Error rate differential
        base_err_rate = baseline_errors_count / float(n1)
        canary_err_rate = canary_errors_count / float(n2)
        err_delta = canary_err_rate - base_err_rate

        # 2. Two-sample Kolmogorov-Smirnov test
        d_stat, p_val = self._compute_two_sample_ks(s_base, s_canary)

        # Critical value c(alpha) * sqrt((n1 + n2)/(n1 * n2))
        # c(0.01) = 1.63, c(0.05) = 1.36
        c_alpha = 1.63 if self.alpha <= 0.01 else 1.36
        d_crit = c_alpha * math.sqrt((n1 + n2) / float(n1 * n2))

        # Check for degradation triggers
        rollback = False
        reasons: List[str] = []

        if err_delta > self.max_err_delta:
            rollback = True
            reasons.append(f"Canary error rate spike: +{err_delta*100:.2f}% exceeds allowed +{self.max_err_delta*100:.2f}%")

        if d_stat > self.ks_ceiling:
            rollback = True
            reasons.append(f"Extreme KS distributional drift: D={d_stat:.4f} > ceiling={self.ks_ceiling:.4f}")

        if (d_stat > d_crit) and (p_val < self.alpha):
            if err_delta > 0.005:  # Drift correlated with worsening performance
                rollback = True
                reasons.append(f"Statistically significant distribution drift (p={p_val:.4e} < alpha={self.alpha}) with error degradation.")

        if rollback:
            verdict = CanaryVerdict.CANARY_DEGRADED_ROLLBACK
            reason_str = " | ".join(reasons)
        elif d_stat > (d_crit * 0.8):
            verdict = CanaryVerdict.CANARY_MARGINAL_MONITOR
            reason_str = f"Marginal drift detected (D={d_stat:.4f}, D_crit={d_crit:.4f}). Continue soak testing."
        else:
            verdict = CanaryVerdict.CANARY_HEALTHY_PROCEED
            reason_str = f"Canary passed all statistical KS and error rate gates (D={d_stat:.4f} <= {d_crit:.4f})."

        return CanaryEvaluationReport(
            step_name=step_name,
            traffic_weight_percent=traffic_weight_percent,
            sample_size_baseline=n1,
            sample_size_canary=n2,
            ks_statistic=round(d_stat, 4),
            ks_critical_value=round(d_crit, 4),
            p_value=round(p_val, 6),
            baseline_error_rate=round(base_err_rate, 4),
            canary_error_rate=round(canary_err_rate, 4),
            error_rate_delta=round(err_delta, 4),
            verdict=verdict,
            rollback_triggered=rollback,
            reason=reason_str,
        )
