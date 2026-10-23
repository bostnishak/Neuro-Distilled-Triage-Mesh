"""Unit tests for Neuro-Symbolic Z3 SMT Theorem Prover and unsat_core conflict analysis."""
from __future__ import annotations

from uuid import uuid4

import pytest

from backend.schemas.symbolic import FieldTeamDTO, IncidentTaskDTO, TaskAssignmentDTO
from backend.services.z3_symbolic_solver import (
    NeuroSymbolicZ3Solver,
    haversine_travel_minutes,
)


class TestHaversineDistance:
    """Verifies Haversine travel time calculation."""

    def test_same_coordinates_zero_distance(self):
        # Even at 0km, returns minimum 5 minutes baseline response time
        minutes = haversine_travel_minutes(41.0082, 28.9784, 41.0082, 28.9784)
        assert minutes == 5

    def test_known_distance_travel_time(self):
        # Kadıköy (40.99) to Taksim (41.03): ~6 km (at 40km/h ~8-10 min)
        minutes = haversine_travel_minutes(40.99, 29.02, 41.03, 28.98)
        assert 5 <= minutes <= 30


class TestZ3VerificationAndUnsatCore:
    """Verifies Z3 Boolean tracked guards and unsat_core conflict extraction."""

    def setup_method(self):
        self.solver = NeuroSymbolicZ3Solver(max_iterations=3)

        self.team_alpha = FieldTeamDTO(
            id=uuid4(),
            team_code="ALPHA-1",
            skills=["HIGH_VOLTAGE_SAFETY", "ELECTRICAL"],
            shift_remaining_minutes=180,
            max_concurrent_tasks=2,
            latitude=41.008,
            longitude=28.978,
            is_available=True,
        )

        self.team_bravo = FieldTeamDTO(
            id=uuid4(),
            team_code="BRAVO-2",
            skills=["HAZMAT_CONTAINMENT"],
            shift_remaining_minutes=60,
            max_concurrent_tasks=1,
            latitude=41.015,
            longitude=28.980,
            is_available=True,
        )

        self.inc_electrical = IncidentTaskDTO(
            id=uuid4(),
            category="POWER_GRID_FAILURE",
            required_skills=["HIGH_VOLTAGE_SAFETY"],
            latitude=41.009,
            longitude=28.979,
            urgency_score=5,
            estimated_work_minutes=45,
        )

        self.inc_gas = IncidentTaskDTO(
            id=uuid4(),
            category="GAS_LEAK",
            required_skills=["HAZMAT_CONTAINMENT"],
            latitude=41.014,
            longitude=28.982,
            urgency_score=6,
            estimated_work_minutes=40,
        )

    def test_sat_valid_proposal(self):
        # Valid assignment: Electrical -> Alpha, Gas -> Bravo
        proposal = [
            TaskAssignmentDTO(
                incident_id=self.inc_electrical.id,
                team_id=self.team_alpha.id,
                estimated_travel_minutes=5,
                estimated_work_minutes=45,
                arrival_time_minutes=5,
            ),
            TaskAssignmentDTO(
                incident_id=self.inc_gas.id,
                team_id=self.team_bravo.id,
                estimated_travel_minutes=5,
                estimated_work_minutes=40,
                arrival_time_minutes=5,
            ),
        ]

        is_sat, unsat_core, proof = self.solver.verify_proposal_with_unsat_core(
            incidents=[self.inc_electrical, self.inc_gas],
            teams=[self.team_alpha, self.team_bravo],
            proposal=proposal,
        )

        assert is_sat is True
        assert len(unsat_core) == 0
        assert "(check-sat)" in proof or len(proof) > 0

    def test_unsat_skill_mismatch_extraction(self):
        # Invalid assignment: Gas Leak -> Alpha (Alpha lacks HAZMAT skill!)
        proposal = [
            TaskAssignmentDTO(
                incident_id=self.inc_gas.id,
                team_id=self.team_alpha.id,
                estimated_travel_minutes=5,
                estimated_work_minutes=40,
                arrival_time_minutes=5,
            ),
            TaskAssignmentDTO(
                incident_id=self.inc_electrical.id,
                team_id=self.team_bravo.id,
                estimated_travel_minutes=5,
                estimated_work_minutes=45,
                arrival_time_minutes=5,
            ),
        ]

        is_sat, unsat_core, _ = self.solver.verify_proposal_with_unsat_core(
            incidents=[self.inc_electrical, self.inc_gas],
            teams=[self.team_alpha, self.team_bravo],
            proposal=proposal,
        )

        assert is_sat is False
        assert len(unsat_core) > 0
        # The unsat core must pinpoint the exact skill mismatch clause!
        assert any("SKILL_MISMATCH" in clause for clause in unsat_core)

    def test_z3_optimize_fallback_synthesis(self):
        # Full synthesis using Z3 Optimize
        assignments, proof = self.solver.solve_optimal_z3(
            incidents=[self.inc_electrical, self.inc_gas],
            teams=[self.team_alpha, self.team_bravo],
        )

        assert len(assignments) == 2
        assigned_map = {a.incident_id: a.team_id for a in assignments}
        # Mathematical constraint guarantee: Electrical must go to Alpha, Gas must go to Bravo
        assert assigned_map[self.inc_electrical.id] == self.team_alpha.id
        assert assigned_map[self.inc_gas.id] == self.team_bravo.id
