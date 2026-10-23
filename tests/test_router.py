"""Unit tests for Module 2: DistillMesh Semantic Router decision logic."""
from services.router_service import (
    RouterThresholds,
    RouteTarget,
    StudentOutput,
    TriagePrediction,
    decide_route,
)


def test_router_confident_in_distribution():
    th = RouterThresholds(confidence=0.80, margin=0.15, ood_similarity=0.70)
    pred = TriagePrediction(
        intent="road_damage",
        confidence=0.92,
        urgency=0.6,
        priority=2,
    )
    student = StudentOutput(
        prediction=pred,
        margin=0.35,
        truncated=False,
        latency_ms=4.1,
    )

    route, reasons = decide_route(student, ood_similarity=0.88, th=th)
    assert route == RouteTarget.STUDENT
    assert "confident_in_distribution" in reasons


def test_router_escalates_on_low_confidence():
    th = RouterThresholds(confidence=0.80, margin=0.15, ood_similarity=0.70)
    pred = TriagePrediction(
        intent="water_leak",
        confidence=0.68,  # Below 0.80
        urgency=0.5,
        priority=2,
    )
    student = StudentOutput(
        prediction=pred,
        margin=0.25,
        truncated=False,
        latency_ms=4.0,
    )

    route, reasons = decide_route(student, ood_similarity=0.85, th=th)
    assert route == RouteTarget.TEACHER
    assert any("low_confidence" in r for r in reasons)


def test_router_escalates_on_ambiguous_margin():
    th = RouterThresholds(confidence=0.80, margin=0.15, ood_similarity=0.70)
    pred = TriagePrediction(
        intent="power_outage",
        confidence=0.82,
        urgency=0.7,
        priority=2,
    )
    student = StudentOutput(
        prediction=pred,
        margin=0.08,  # Below 0.15
        truncated=False,
        latency_ms=4.2,
    )

    route, reasons = decide_route(student, ood_similarity=0.85, th=th)
    assert route == RouteTarget.TEACHER
    assert any("ambiguous_margin" in r for r in reasons)


def test_router_escalates_on_ood_similarity():
    th = RouterThresholds(confidence=0.80, margin=0.15, ood_similarity=0.70)
    pred = TriagePrediction(
        intent="streetlight_failure",
        confidence=0.85,
        urgency=0.4,
        priority=3,
    )
    student = StudentOutput(
        prediction=pred,
        margin=0.30,
        truncated=False,
        latency_ms=4.0,
    )

    # Cosine similarity to nearest prototype is only 0.52 (Out of distribution)
    route, reasons = decide_route(student, ood_similarity=0.52, th=th)
    assert route == RouteTarget.TEACHER
    assert any("out_of_distribution" in r for r in reasons)
