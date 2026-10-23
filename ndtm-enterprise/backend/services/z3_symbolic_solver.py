"""Saha ekiplerini arıza ihbarlarına atayan Z3 kısıt çözücü servisi.
LLM'lerin vardiya ve sertifika kurallarını çiğnemesini önlemek için kuralları Z3 solver üzerinde doğrular.
"""
from __future__ import annotations

import logging
import math
import time
from typing import Sequence
from uuid import UUID

import z3

from backend.core.config import get_settings
from backend.schemas.symbolic import (
    FieldTeamDTO,
    IncidentTaskDTO,
    IterationAuditLog,
    TaskAssignmentDTO,
    Z3SolveResponse,
)

logger = logging.getLogger("services.z3_solver")
settings = get_settings()


def haversine_travel_minutes(lat1: float, lon1: float, lat2: float, lon2: float, avg_speed_kmh: float = 40.0) -> int:
    """İki GPS koordinatı arasındaki tahmini sürüş süresini hesaplar.
    Şehir içi ortalama hız 40 km/s baz alınır. Trafik ve park payı için minimum 5 dakika atanır.
    """
    r = 6371.0  # Dünya yarıçapı (km)
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    dist_km = r * c

    hours = dist_km / max(10.0, avg_speed_kmh)
    return max(5, int(hours * 60.0))


class NeuroSymbolicZ3Solver:
    """Z3 tabanlı saha atama doğrulayıcı ve kısıt optimize edici."""

    def __init__(self, max_iterations: int = 3) -> None:
        self.max_iterations = max_iterations

    def verify_proposal_with_unsat_core(
        self,
        incidents: list[IncidentTaskDTO],
        teams: list[FieldTeamDTO],
        proposal: list[TaskAssignmentDTO],
    ) -> tuple[bool, list[str], str]:
        """Formal mathematical verification with tracked Boolean guards to extract unsat_core."""
        s = z3.Solver()
        s.set(unsat_core=True)

        team_map = {t.id: t for t in teams}
        incident_map = {i.id: i for i in incidents}

        assigned_incidents: set[UUID] = set()
        team_workload: dict[UUID, int] = {t.id: 0 for t in teams}
        team_tasks_count: dict[UUID, int] = {t.id: 0 for t in teams}

        for assignment in proposal:
            inc = incident_map.get(assignment.incident_id)
            team = team_map.get(assignment.team_id)
            if not inc or not team:
                continue

            assigned_incidents.add(inc.id)
            travel_min = haversine_travel_minutes(team.latitude, team.longitude, inc.latitude, inc.longitude)
            total_time = travel_min + inc.estimated_work_minutes

            team_workload[team.id] += total_time
            team_tasks_count[team.id] += 1

            # C2: Skill Compatibility Guard
            has_skills = all(skill in team.skills for skill in inc.required_skills)
            skill_guard = f"SKILL_MISMATCH_INC_{str(inc.id)[:8]}_TEAM_{team.team_code}"
            s.assert_and_track(z3.BoolVal(has_skills), skill_guard)

            # C4: Critical Urgency SLA Guard
            if inc.urgency_score >= 8:
                sla_guard = f"SLA_VIOLATION_INC_{str(inc.id)[:8]}"
                meets_sla = assignment.arrival_time_minutes <= settings.CRITICAL_URGENCY_SLA_MINUTES
                s.assert_and_track(z3.BoolVal(meets_sla), sla_guard)

        # C1: Exclusivity Guard
        for inc in incidents:
            assigned = inc.id in assigned_incidents
            excl_guard = f"UNASSIGNED_INCIDENT_{str(inc.id)[:8]}"
            s.assert_and_track(z3.BoolVal(assigned), excl_guard)

        # C3 & C5: Shift Capacity and Concurrency Guards
        for team in teams:
            shift_guard = f"SHIFT_OVERFLOW_TEAM_{team.team_code}"
            within_shift = team_workload[team.id] <= team.shift_remaining_minutes
            s.assert_and_track(z3.BoolVal(within_shift), shift_guard)

            concurrency_guard = f"CONCURRENCY_EXCEEDED_TEAM_{team.team_code}"
            within_cap = team_tasks_count[team.id] <= team.max_concurrent_tasks
            s.assert_and_track(z3.BoolVal(within_cap), concurrency_guard)

        # Evaluate SAT vs UNSAT
        check_result = s.check()
        if check_result == z3.sat:
            return True, [], s.to_smt2()
        else:
            core = [str(clause) for clause in s.unsat_core()]
            return False, core, s.to_smt2()

    def solve_optimal_z3(
        self,
        incidents: list[IncidentTaskDTO],
        teams: list[FieldTeamDTO],
    ) -> tuple[list[TaskAssignmentDTO], str]:
        """Synthesizes mathematically proven optimal schedule using z3.Optimize()."""
        opt = z3.Optimize()
        num_incidents = len(incidents)
        num_teams = len(teams)

        if num_incidents == 0 or num_teams == 0:
            return [], "(assert true)"

        # Binary decision variables x[i, j] in {0, 1}
        x = {}
        travel_times = {}

        for i, inc in enumerate(incidents):
            for j, team in enumerate(teams):
                x[i, j] = z3.Int(f"assign_{i}_{j}")
                opt.add(z3.Or(x[i, j] == 0, x[i, j] == 1))

                # Hard Skill Constraint
                has_skills = all(skill in team.skills for skill in inc.required_skills)
                if not has_skills:
                    opt.add(x[i, j] == 0)

                travel_times[i, j] = haversine_travel_minutes(
                    team.latitude, team.longitude, inc.latitude, inc.longitude
                )

                # Critical SLA constraint (urgency >= 8 -> arrival <= 45m)
                if inc.urgency_score >= 8:
                    if travel_times[i, j] > settings.CRITICAL_URGENCY_SLA_MINUTES:
                        opt.add(x[i, j] == 0)

            # C1: Each incident assigned to at most one team
            opt.add(z3.Sum([x[i, j] for j in range(num_teams)]) <= 1)

        # Team shift and concurrency constraints
        for j, team in enumerate(teams):
            total_time = [
                x[i, j] * (incidents[i].estimated_work_minutes + travel_times[i, j])
                for i in range(num_incidents)
            ]
            opt.add(z3.Sum(total_time) <= team.shift_remaining_minutes)
            opt.add(z3.Sum([x[i, j] for i in range(num_incidents)]) <= team.max_concurrent_tasks)

        # Objective Function: Maximize weighted priority fulfillment and minimize travel time
        objective_terms = []
        for i, inc in enumerate(incidents):
            for j in range(num_teams):
                # Weight by incident urgency (scale 1..10) minus small travel penalty
                weight = (inc.urgency_score * 100) - travel_times[i, j]
                objective_terms.append(x[i, j] * weight)

        opt.maximize(z3.Sum(objective_terms))

        if opt.check() != z3.sat:
            return [], str(opt)

        model = opt.model()
        solution: list[TaskAssignmentDTO] = []

        for i, inc in enumerate(incidents):
            for j, team in enumerate(teams):
                if model[x[i, j]].as_long() == 1:
                    travel = travel_times[i, j]
                    solution.append(
                        TaskAssignmentDTO(
                            incident_id=inc.id,
                            team_id=team.id,
                            estimated_travel_minutes=travel,
                            estimated_work_minutes=inc.estimated_work_minutes,
                            arrival_time_minutes=travel,
                        )
                    )
                    break

        return solution, str(opt)

    def execute_self_correcting_loop(
        self,
        incidents: list[IncidentTaskDTO],
        teams: list[FieldTeamDTO],
        initial_proposal: list[TaskAssignmentDTO] | None = None,
    ) -> Z3SolveResponse:
        """Executes iterative verification, unsat_core counter-example generation, and optimal fallback."""
        start_time = time.perf_counter()
        history: list[IterationAuditLog] = []

        current_proposal = initial_proposal

        # Iterative Loop (Max 3 rounds)
        for iteration in range(1, self.max_iterations + 1):
            if current_proposal is None:
                break

            is_sat, unsat_core, proof_smt2 = self.verify_proposal_with_unsat_core(
                incidents, teams, current_proposal
            )

            history.append(
                IterationAuditLog(
                    iteration=iteration,
                    status="SAT" if is_sat else "UNSAT",
                    unsat_core_conflicts=unsat_core,
                    proposal=current_proposal,
                )
            )

            if is_sat:
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                status_str = "VERIFIED" if iteration == 1 else "REPAIRED"
                logger.info("Schedule proposal mathematically verified (%s) in %d iteration(s).", status_str, iteration)
                return Z3SolveResponse(
                    is_sat=True,
                    status=status_str,
                    assignments=current_proposal,
                    unsat_core_conflicts=[],
                    iteration_history=history,
                    iterations_executed=iteration,
                    z3_proof_smt2=proof_smt2,
                    solver_time_ms=round(elapsed_ms, 2),
                )

            logger.warning(
                "Iteration %d returned UNSAT. Conflicts: %s. Attempting repair mutation...",
                iteration,
                unsat_core,
            )

            # Heuristic mutation: Remove conflicting assignments highlighted by unsat_core
            conflicted_ids: set[str] = set()
            for conflict in unsat_core:
                for token in conflict.split("_"):
                    if len(token) == 8:
                        conflicted_ids.add(token)

            current_proposal = [
                a for a in current_proposal if str(a.incident_id)[:8] not in conflicted_ids
            ]

        # Fallback to Z3 Optimize solver for guaranteed mathematically optimal plan
        logger.info("Iterative proposal loop exhausted. Executing Z3 Optimize solver...")
        optimal_assignments, proof_smt2 = self.solve_optimal_z3(incidents, teams)
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        history.append(
            IterationAuditLog(
                iteration=len(history) + 1,
                status="SAT" if optimal_assignments else "UNSAT_FATAL",
                unsat_core_conflicts=[],
                proposal=optimal_assignments,
            )
        )

        return Z3SolveResponse(
            is_sat=bool(optimal_assignments),
            status="Z3_OPTIMIZED" if optimal_assignments else "UNSAT_FATAL",
            assignments=optimal_assignments,
            unsat_core_conflicts=[],
            iteration_history=history,
            iterations_executed=len(history),
            z3_proof_smt2=proof_smt2,
            solver_time_ms=round(elapsed_ms, 2),
        )
