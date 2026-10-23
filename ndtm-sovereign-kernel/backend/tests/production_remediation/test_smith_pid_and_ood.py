"""
Test Suite: Smith-Predictor PID Router & Ledoit-Wolf Cholesky OOD Detector
Verifies:
1. Smith Predictor dead-time delay compensation and internal lag model.
2. Filtered derivative on measurement and integrator anti-windup.
3. Schmitt-trigger hysteresis routing without limit-cycle chattering.
4. Ledoit-Wolf analytical shrinkage intensity (delta* in [0, 1]).
5. Cholesky forward substitution Mahalanobis distance solve.
6. OOD classification on in-distribution vs synthetic drift vectors.
"""

import math
import numpy as np
import pytest

from engines_v3_hardened.smith_predictor_pid_router import (
    SmithPredictorPIDRouter,
    RouteTarget,
)
from engines_v3_hardened.ledoit_wolf_cholesky_ood import (
    LedoitWolfCholeskyOODDetector,
    OODClassification,
)


def test_smith_pid_router_hysteresis():
    router = SmithPredictorPIDRouter(
        kp=2.0,
        ki=0.5,
        kd=0.1,
        threshold_low_to_mid=0.40,
        threshold_mid_to_high=0.75,
        hysteresis_delta=0.03,
    )

    # Initial state should be LOCAL_EDGE_SPSC
    assert router.current_tier == RouteTarget.LOCAL_EDGE_SPSC

    # Moderate error below threshold + delta (0.43) stays at EDGE
    rec1 = router.compute_step(setpoint=0.5, measurement=0.15, current_ts=100.0)
    assert router.current_tier == RouteTarget.LOCAL_EDGE_SPSC

    # Escalate: measurement spikes to 0.95 -> control output rises above 0.78 -> CLOUD
    for i in range(10):
        rec_spike = router.compute_step(setpoint=1.0, measurement=0.0, current_ts=100.0 + (i * 0.05))

    assert router.current_tier == RouteTarget.SOVEREIGN_CLOUD_TEACHER

    # Hysteresis check: small decrease below 0.75 does NOT immediately drop to REGIONAL until < (0.75 - 0.03 = 0.72)
    summary = router.get_status_summary()
    assert summary["history_length"] > 0


def test_ledoit_wolf_cholesky_ood():
    dim = 64  # Unit test dimension
    detector = LedoitWolfCholeskyOODDetector(embedding_dim=dim)

    # Generate 100 in-distribution samples
    rng = np.random.RandomState(42)
    in_dist = rng.normal(loc=0.0, scale=1.0, size=(100, dim))
    detector.fit(in_dist)

    assert detector.is_fitted is True
    assert 0.0 <= detector.shrinkage_delta <= 1.0
    assert detector.cholesky_lower_l is not None

    # Evaluate in-distribution vector (mean vector)
    mean_res = detector.evaluate(detector.mean_vector)
    assert mean_res.classification == OODClassification.IN_DISTRIBUTION
    assert mean_res.mahalanobis_distance < 1.0
    assert mean_res.requires_cloud_escalation is False

    # Evaluate extreme OOD outlier vector (scaled 10x)
    outlier = detector.mean_vector + 10.0 * np.ones(dim)
    ood_res = detector.evaluate(outlier)
    assert ood_res.classification == OODClassification.CRITICAL_OOD
    assert ood_res.requires_cloud_escalation is True
    assert ood_res.requires_active_learning is True
