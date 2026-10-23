import datetime
import uuid
import pytest
from domain.services.hawkes_process_engine import (
    HawkesProcessEngine,
    HawkesParameters,
    HawkesHistoricalEvent,
)
from domain.services.smt_pareto_dispatcher import SmtParetoDispatcher
from domain.entities import IncidentEntity, FieldTeamEntity
from domain.value_objects import GeoCoordinates


def test_hawkes_mathematical_kernel():
    params = HawkesParameters(mu=0.01, alpha=0.4, beta=0.002, sigma_meters=500.0)
    engine = HawkesProcessEngine(params)

    assert params.branching_ratio == 200.0  # alpha / beta
    assert engine.temporal_decay(0.0) == 1.0
    assert engine.temporal_decay(500.0) < 0.4

    # Spatial kernel peak at d=0
    peak_spatial = engine.spatial_kernel(0.0)
    dispersed_spatial = engine.spatial_kernel(500.0)
    assert peak_spatial > dispersed_spatial

    loc1 = GeoCoordinates(latitude=41.0082, longitude=28.9784)
    history = [HawkesHistoricalEvent(timestamp_seconds=100.0, location=loc1, magnitude=1.0)]

    # Compute intensity at t=200
    intensity = engine.conditional_intensity(current_time_sec=200.0, target_location=loc1, history=history)
    assert intensity > params.mu

    # Compute aftershock probability in next 1 hour
    prob = engine.compute_aftershock_probability(
        current_time_sec=200.0, target_location=loc1, history=history, horizon_seconds=3600.0
    )
    assert 0.0 <= prob <= 1.0


def test_z3_maxsmt_pareto_dispatcher():
    dispatcher = SmtParetoDispatcher(solver_timeout_ms=3000)

    now = datetime.datetime.now(datetime.timezone.utc)
    inc1 = IncidentEntity(
        id=uuid.uuid4(),
        title="BOTAŞ Gas Pressure Anomaly",
        description_scrubbed="Gas pressure spike detected",
        urgency="CRITICAL",
        category="GAS_PIPELINE",
        modality="TEXT_ONLY",
        source_protocol="SCADA",
        location=GeoCoordinates(latitude=41.0082, longitude=28.9784),
        triage_state="TRIAGED",
        created_at=now,
        updated_at=now,
    )

    team_idle = FieldTeamEntity(
        id=uuid.uuid4(),
        team_name="İGDAŞ Acil Müdahale Tim-1",
        specialization="GAS_HAZMAT",
        current_location=GeoCoordinates(latitude=41.0100, longitude=28.9800),
        status="IDLE",
        shift_start_hour=8,
        shift_end_hour=20,
        burnout_index=0.20,
        cumulative_shifts_week=2,
        created_at=now,
        updated_at=now,
    )

    team_exhausted = FieldTeamEntity(
        id=uuid.uuid4(),
        team_name="İGDAŞ Acil Müdahale Tim-2",
        specialization="GAS_HAZMAT",
        current_location=GeoCoordinates(latitude=41.0083, longitude=28.9785),
        status="IDLE",
        shift_start_hour=8,
        shift_end_hour=20,
        burnout_index=0.95,  # Excluded by hard invariant (> 0.85)
        cumulative_shifts_week=6,
        created_at=now,
        updated_at=now,
    )

    assignments = dispatcher.optimize_dispatch(
        incidents=[inc1],
        teams=[team_idle, team_exhausted],
        current_hour=14,
    )

    assert len(assignments) == 1
    matched_inc, matched_team, eta, proof = assignments[0]

    assert matched_inc.id == inc1.id
    # Must assign team_idle because team_exhausted violates burnout barrier
    assert matched_team.id == team_idle.id
    assert eta > 0.0
    assert proof.is_sat is True
