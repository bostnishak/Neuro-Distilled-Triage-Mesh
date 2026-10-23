"""Tests for continuous model evaluation and shadow testing divergence scoring."""
from services.router_service import TriagePrediction
from services.shadow_testing import compute_divergence_score


def test_divergence_score_perfect_match():
    student = TriagePrediction(
        intent="road_damage",
        confidence=0.92,
        urgency=0.7,
        priority=2,
    )
    teacher = TriagePrediction(
        intent="road_damage",
        confidence=0.95,
        urgency=0.7,
        priority=2,
    )

    intent_match, urgency_delta, divergence_score = compute_divergence_score(student, teacher)

    assert intent_match is True
    assert urgency_delta == 0.0
    assert divergence_score == 0.0


def test_divergence_score_intent_mismatch():
    student = TriagePrediction(
        intent="streetlight_failure",
        confidence=0.82,
        urgency=0.3,
        priority=3,
    )
    teacher = TriagePrediction(
        intent="power_outage",
        confidence=0.88,
        urgency=0.7,
        priority=2,
    )

    intent_match, urgency_delta, divergence_score = compute_divergence_score(student, teacher)

    assert intent_match is False
    assert urgency_delta == 0.4
    # Score should include 0.65 penalty for intent mismatch + 0.4 * 0.35 urgency penalty = 0.79
    assert divergence_score >= 0.65
