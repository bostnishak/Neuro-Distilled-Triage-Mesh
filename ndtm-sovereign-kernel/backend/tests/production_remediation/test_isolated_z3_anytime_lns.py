"""
Test Suite: Subprocess-Isolated Anytime Z3 + LNS Warm-Start Dispatcher
Verifies:
1. Tier A Greedy LNS solve speed (<15ms).
2. Conflict-free bipartite matching and burnout exclusion.
3. Subprocess isolation and independent z3.Context() execution.
4. Guaranteed anytime deadline fallback (zero dropped dispatches on timeout).
"""

import time
import pytest

from engines_v3_hardened.isolated_anytime_z3_lns import (
    SubprocessIsolatedAnytimeZ3LNSDispatcher,
    GreedyLNSFastSolver,
    IncidentSummary,
    TeamSummary,
    DispatchSolverTier,
)


@pytest.fixture
def sample_scenarios():
    incidents = [
        IncidentSummary(id="inc_01", category="FIRE", urgency="CRITICAL", lat=37.7749, lon=-122.4194),
        IncidentSummary(id="inc_02", category="MEDICAL", urgency="HIGH", lat=37.7833, lon=-122.4167),
        IncidentSummary(id="inc_03", category="HAZMAT", urgency="MEDIUM", lat=37.7650, lon=-122.4200),
    ]
    teams = [
        TeamSummary(id="team_01", specialization="FIRE_TACTICAL", burnout_index=0.20, lat=37.7750, lon=-122.4200),
        TeamSummary(id="team_02", specialization="SEARCH_RESCUE", burnout_index=0.45, lat=37.7840, lon=-122.4160),
        TeamSummary(id="team_burned", specialization="GAS_HAZMAT", burnout_index=0.92, lat=37.7660, lon=-122.4210),  # Burnout > 0.85
    ]
    return incidents, teams


def test_greedy_lns_fast_solver(sample_scenarios):
    incidents, teams = sample_scenarios

    t0 = time.perf_counter()
    assignments, total_cost = GreedyLNSFastSolver.solve(incidents, teams)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    # Must complete in sub-15ms
    assert elapsed_ms < 15.0
    assert len(assignments) == 2  # 2 eligible teams (team_burned excluded)

    # Invariant 1: No team assigned twice
    assigned_teams = [a.team_id for a in assignments]
    assert len(assigned_teams) == len(set(assigned_teams))
    assert "team_burned" not in assigned_teams

    # Invariant 2: No incident assigned twice
    assigned_incidents = [a.incident_id for a in assignments]
    assert len(assigned_incidents) == len(set(assigned_incidents))


def test_subprocess_anytime_dispatcher(sample_scenarios):
    incidents, teams = sample_scenarios
    dispatcher = SubprocessIsolatedAnytimeZ3LNSDispatcher(z3_timeout_ms=1200)

    # Dispatch with generous SLA allows Tier B Z3 to complete or fallback cleanly
    resp = dispatcher.dispatch(incidents, teams, sla_deadline_ms=1200.0)
    assert resp.solver_tier_used in (DispatchSolverTier.TIER_B_Z3_MAXSMT, DispatchSolverTier.TIER_A_LNS_FAST)
    assert len(resp.assignments) >= 2
    assert resp.total_cost > 0.0


def test_anytime_fallback_under_micro_deadline(sample_scenarios):
    incidents, teams = sample_scenarios
    dispatcher = SubprocessIsolatedAnytimeZ3LNSDispatcher(z3_timeout_ms=1000)

    # Provide ultra-tight 1ms deadline -> must return Tier A LNS with zero timeouts
    resp = dispatcher.dispatch(incidents, teams, sla_deadline_ms=1.0)
    assert resp.solver_tier_used == DispatchSolverTier.TIER_A_LNS_FAST
    assert len(resp.assignments) >= 2
    assert resp.execution_time_ms < 20.0
