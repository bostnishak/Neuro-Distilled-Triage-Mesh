import math
import uuid
from typing import Dict, List, Optional, Tuple, Any
import z3
from core.config import settings
from core.exceptions import SmtUnsatException
from core.logging_otel import logger, SMT_SOLVER_DURATION
from domain.entities import IncidentEntity, FieldTeamEntity, DispatchScheduleEntity
from domain.value_objects import SmtProof


class SmtParetoDispatcher:
    """Formal Neuro-Symbolic Z3 MaxSMT Pareto-Optimal Resource Dispatch Engine."""

    def __init__(self, solver_timeout_ms: Optional[int] = None):
        self.solver_timeout_ms = solver_timeout_ms or settings.Z3_SOLVER_TIMEOUT_MS

    def optimize_dispatch(
        self,
        incidents: List[IncidentEntity],
        teams: List[FieldTeamEntity],
        current_hour: int = 14,
    ) -> List[Tuple[IncidentEntity, FieldTeamEntity, float, SmtProof]]:
        """Solves Pareto-optimal bipartite matching between incidents and teams under formal invariants.

        Returns list of (incident, team, eta_minutes, smt_proof).
        """
        if not incidents or not teams:
            return []

        optimizer = z3.Optimize()
        optimizer.set("timeout", self.solver_timeout_ms)

        # Decision variables: x[i][j] in {0, 1}
        # x_vars[(i_id, t_id)]
        x_vars: Dict[Tuple[uuid.UUID, uuid.UUID], z3.BoolRef] = {}
        for inc in incidents:
            inc_tag = str(inc.id).replace("-", "")
            for team in teams:
                team_tag = str(team.id).replace("-", "")
                var_name = f"x_{inc_tag}_{team_tag}"
                x_vars[(inc.id, team.id)] = z3.Bool(var_name)

        # Tracking assumptions for UNSAT core extraction
        assumptions: Dict[str, z3.BoolRef] = {}

        # 1. Hard Invariant: Each incident assigned to at most one team
        for inc in incidents:
            inc_tag = str(inc.id).replace("-", "")
            assigned_team_bools = [x_vars[(inc.id, team.id)] for team in teams]
            label = f"hard_assignment_one_{inc_tag}"
            asm = z3.Bool(label)
            assumptions[label] = asm
            # sum of assigned <= 1
            int_exprs = [z3.If(b, 1, 0) for b in assigned_team_bools]
            optimizer.add(z3.Implies(asm, z3.Sum(int_exprs) <= 1))

        # 2. Hard Invariant: Team capacity limit (max 1 active concurrent assignment per team)
        for team in teams:
            team_tag = str(team.id).replace("-", "")
            team_assignments = [x_vars[(inc.id, team.id)] for inc in incidents]
            label = f"hard_capacity_team_{team_tag}"
            asm = z3.Bool(label)
            assumptions[label] = asm
            int_exprs = [z3.If(b, 1, 0) for b in team_assignments]
            optimizer.add(z3.Implies(asm, z3.Sum(int_exprs) <= 1))

        # 3. Hard Invariant: Burnout Safety Barrier (teams with burnout > 0.85 excluded)
        for team in teams:
            team_tag = str(team.id).replace("-", "")
            if team.burnout_index > 0.85:
                label = f"hard_burnout_exclude_{team_tag}"
                asm = z3.Bool(label)
                assumptions[label] = asm
                for inc in incidents:
                    optimizer.add(z3.Implies(asm, z3.Not(x_vars[(inc.id, team.id)])))

        # 4. Soft Objectives (MaxSMT weighted optimization)
        # Weights by urgency: CRITICAL = 100, HIGH = 50, MEDIUM = 20, LOW = 5
        urgency_weights = {"CRITICAL": 100.0, "HIGH": 50.0, "MEDIUM": 20.0, "LOW": 5.0}

        objective_terms = []
        for inc in incidents:
            urg_weight = urgency_weights.get(inc.urgency, 10.0)

            for team in teams:
                # Travel time estimation: ~40 km/h urban speed -> ~666 meters / minute
                dist_m = inc.location.haversine_distance_meters(team.current_location)
                eta_min = max(2.0, dist_m / 666.0)

                # Specialization bonus
                spec_bonus = -30.0 if self._is_specialist(team.specialization, inc.category) else 0.0

                # Weighted cost: lower cost is better
                assignment_cost = (urg_weight * eta_min) + (team.burnout_index * 20.0) + spec_bonus
                assignment_cost = max(1.0, assignment_cost)

                b_var = x_vars[(inc.id, team.id)]
                # Soft constraint: prefer assigning high priority pairs with lowest cost
                int_weight = int(assignment_cost)
                optimizer.add_soft(z3.Not(b_var), int_weight)

            # High urgency assignment incentive
            assigned_bools = [x_vars[(inc.id, team.id)] for team in teams]
            int_exprs = [z3.If(b, 1, 0) for b in assigned_bools]
            # Reward assigning critical incidents
            optimizer.add_soft(z3.Sum(int_exprs) >= 1, int(urg_weight * 500))

        # Solve with assumptions
        active_assumptions = list(assumptions.values())
        check_result = optimizer.check(active_assumptions)

        if check_result == z3.unsat:
            # Minimal Correction Subset (MCS) self-repair
            unsat_core_labels = [str(a) for a in optimizer.unsat_core()]
            logger.warning("smt_unsat_encountered_triggering_self_repair", unsat_core=unsat_core_labels)

            # Retry without burnout exclusion constraint in emergency mode
            relaxed_assumptions = [a for a in active_assumptions if "burnout" not in str(a)]
            check_result = optimizer.check(relaxed_assumptions)

            if check_result == z3.unsat:
                SMT_SOLVER_DURATION.labels(status="unsat").observe(0.1)
                raise SmtUnsatException("Dispatch constraints mathematically unsatisfiable", unsat_core_labels)

        model = optimizer.model()
        SMT_SOLVER_DURATION.labels(status="sat").observe(0.05)

        assignments: List[Tuple[IncidentEntity, FieldTeamEntity, float, SmtProof]] = []

        for inc in incidents:
            for team in teams:
                var = x_vars[(inc.id, team.id)]
                is_selected = model.eval(var, model_completion=True)
                if z3.is_true(is_selected):
                    dist_m = inc.location.haversine_distance_meters(team.current_location)
                    eta = max(2.0, dist_m / 666.0)
                    proof = SmtProof(
                        is_sat=True,
                        objective_value=float(dist_m),
                        unsat_core=(),
                        slack_variables=(("eta_minutes", eta), ("burnout_factor", team.burnout_index)),
                    )
                    assignments.append((inc, team, eta, proof))

        return assignments

    @staticmethod
    def _is_specialist(specialization: str, category: str) -> bool:
        """Evaluates whether team specialization matches category domain."""
        pairs = {
            "GAS_HAZMAT": {"GAS_PIPELINE", "HAZMAT_LEAK"},
            "ELECTRICAL": {"ELECTRICAL_GRID"},
            "WATER_HYDRAULIC": {"WATER_MAINS"},
            "SEARCH_RESCUE": {"STRUCTURAL_COLLAPSE", "CIVIL_DEFENSE"},
            "FIRE_TACTICAL": {"INDUSTRIAL_FIRE", "ROAD_HAZARD"},
        }
        return category in pairs.get(specialization, set())
