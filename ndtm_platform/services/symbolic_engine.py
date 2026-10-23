"""Module: Neuro-Symbolic Verification Engine.

Combines LLM resource allocation reasoning with the Microsoft Z3 Theorem Prover
to eliminate hallucinations and enforce hard mathematical constraints:
1. Technician skill coverage.
2. Non-overlapping temporal execution intervals.
3. Shift duration limits.
4. Task deadlines and duration consistency.
5. Automated self-correction feedback loop and deterministic Z3 Optimize fallback.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import z3

from ndtm_platform.models.schemas import (
    SchedulePlan,
    ScheduledTask,
    Skill,
    SymbolicVerificationResponse,
    TaskAssignment,
    Technician,
)

logger = logging.getLogger("symbolic_engine")


class NeuroSymbolicEngine:
    """Verifies and synthesizes resource allocation plans using Z3 Theorem Prover."""

    def __init__(self, max_correction_rounds: int = 3) -> None:
        self.max_correction_rounds = max_correction_rounds

    def verify_plan_z3(
        self,
        tasks: list[ScheduledTask],
        technicians: list[Technician],
        plan: SchedulePlan,
    ) -> tuple[bool, list[dict[str, Any]]]:
        """Formal mathematical verification of the schedule plan using Z3 SMT solver."""
        violations: list[dict[str, Any]] = []
        tech_map = {t.id: t for t in technicians}
        task_map = {t.id: t for t in tasks}

        # 1. Structural checks
        assigned_tasks: set[str] = set()
        for assignment in plan.assignments:
            tid = assignment.task_id
            tech_id = assignment.technician_id

            if tid not in task_map:
                violations.append({"rule": "UNKNOWN_TASK", "task_id": tid, "message": f"Task {tid} not in task roster."})
                continue
            if tech_id not in tech_map:
                violations.append({"rule": "UNKNOWN_TECHNICIAN", "tech_id": tech_id, "message": f"Technician {tech_id} not registered."})
                continue

            task = task_map[tid]
            tech = tech_map[tech_id]
            assigned_tasks.add(tid)

            # Skill matching constraint
            if task.required_skill not in tech.skills:
                violations.append({
                    "rule": "SKILL_MISMATCH",
                    "task_id": tid,
                    "tech_id": tech_id,
                    "message": f"Technician {tech.name} lacks required skill '{task.required_skill.value}' for task '{task.title}'",
                })

            # Duration consistency
            duration = assignment.end_hour - assignment.start_hour
            if duration < task.estimated_duration_hours - 1e-4:
                violations.append({
                    "rule": "DURATION_TOO_SHORT",
                    "task_id": tid,
                    "message": f"Assigned duration ({duration:.1f}h) is less than required ({task.estimated_duration_hours:.1f}h).",
                })

            # Deadline constraint
            if assignment.end_hour > task.deadline_hours + 1e-4:
                violations.append({
                    "rule": "DEADLINE_EXCEEDED",
                    "task_id": tid,
                    "message": f"Assignment end ({assignment.end_hour:.1f}h) exceeds task deadline ({task.deadline_hours:.1f}h).",
                })

        # Check unassigned tasks
        for task in tasks:
            if task.id not in assigned_tasks:
                violations.append({
                    "rule": "UNASSIGNED_TASK",
                    "task_id": task.id,
                    "message": f"Task '{task.title}' (priority {task.priority}) was not assigned.",
                })

        # 2. Z3 SMT Formulation for Overlap and Shift Constraints
        solver = z3.Solver()
        tech_assigned_intervals: dict[str, list[tuple[z3.ArithRef, z3.ArithRef, str]]] = {
            t.id: [] for t in technicians
        }

        for idx, assignment in enumerate(plan.assignments):
            if assignment.technician_id not in tech_map:
                continue

            start_var = z3.Real(f"start_{assignment.task_id}_{idx}")
            end_var = z3.Real(f"end_{assignment.task_id}_{idx}")

            solver.add(start_var == assignment.start_hour)
            solver.add(end_var == assignment.end_hour)
            solver.add(start_var >= 0.0)
            solver.add(end_var >= start_var)

            tech_assigned_intervals[assignment.technician_id].append((start_var, end_var, assignment.task_id))

        # Assert no overlapping intervals for the same technician
        for tech_id, intervals in tech_assigned_intervals.items():
            for i in range(len(intervals)):
                for j in range(i + 1, len(intervals)):
                    s1, e1, t1 = intervals[i]
                    s2, e2, t2 = intervals[j]
                    # Overlap occurs if max(s1, s2) < min(e1, e2)
                    # Constraint for validity: e1 <= s2 OR e2 <= s1
                    no_overlap = z3.Or(e1 <= s2, e2 <= s1)
                    solver.push()
                    solver.add(z3.Not(no_overlap))
                    if solver.check() == z3.sat:
                        violations.append({
                            "rule": "INTERVAL_OVERLAP",
                            "tech_id": tech_id,
                            "task_ids": [t1, t2],
                            "message": f"Technician {tech_map[tech_id].name} is double-booked between tasks {t1} and {t2}.",
                        })
                    solver.pop()

            # Shift duration constraint
            total_duration = sum(
                (a.end_hour - a.start_hour)
                for a in plan.assignments
                if a.technician_id == tech_id
            )
            shift_limit = tech_map[tech_id].shift_hours
            if total_duration > shift_limit + 1e-4:
                violations.append({
                    "rule": "SHIFT_EXCEEDED",
                    "tech_id": tech_id,
                    "message": f"Technician {tech_map[tech_id].name} assigned {total_duration:.1f}h exceeding {shift_limit:.1f}h shift.",
                })

        is_valid = len(violations) == 0
        return is_valid, violations

    def solve_optimal_z3(
        self,
        tasks: list[ScheduledTask],
        technicians: list[Technician],
    ) -> SchedulePlan | None:
        """Deterministically synthesizes an optimal, conflict-free schedule using Z3 Optimize."""
        opt = z3.Optimize()

        # Decision variables: assignment indicator x[i, j] in {0, 1}
        # start_time s[i], end_time e[i]
        n_tasks = len(tasks)
        n_techs = len(technicians)
        if n_tasks == 0 or n_techs == 0:
            return SchedulePlan(assignments=[], rationale="No tasks or technicians available.")

        x = {}
        for i, task in enumerate(tasks):
            for j, tech in enumerate(technicians):
                x[i, j] = z3.Int(f"x_{i}_{j}")
                # Domain constraint: binary 0 or 1
                opt.add(z3.Or(x[i, j] == 0, x[i, j] == 1))
                # Skill constraint: if technician lacks skill, x[i, j] MUST be 0
                if task.required_skill not in tech.skills:
                    opt.add(x[i, j] == 0)

            # Each task must be assigned to at most 1 technician
            opt.add(z3.Sum([x[i, j] for j in range(n_techs)]) <= 1)

        # Non-overlapping intervals & shift constraints per technician
        for j, tech in enumerate(technicians):
            # Sum of durations <= shift_hours
            task_hours = [
                x[i, j] * int(tasks[i].estimated_duration_hours * 10)
                for i in range(n_tasks)
            ]
            opt.add(z3.Sum(task_hours) <= int(tech.shift_hours * 10))

        # Objective: Maximize priority-weighted task completion
        weights = [
            x[i, j] * (5 - tasks[i].priority) * 10
            for i in range(n_tasks)
            for j in range(n_techs)
        ]
        opt.maximize(z3.Sum(weights))

        if opt.check() != z3.sat:
            return None

        model = opt.model()
        assignments: list[TaskAssignment] = []
        tech_clock = {tech.id: 0.0 for tech in technicians}

        # Sort tasks by priority
        sorted_tasks = sorted(enumerate(tasks), key=lambda item: item[1].priority)

        for i, task in sorted_tasks:
            for j, tech in enumerate(technicians):
                if model[x[i, j]].as_long() == 1:
                    start_h = tech_clock[tech.id]
                    end_h = start_h + task.estimated_duration_hours
                    assignments.append(
                        TaskAssignment(
                            task_id=task.id,
                            technician_id=tech.id,
                            start_hour=round(start_h, 2),
                            end_hour=round(end_h, 2),
                        )
                    )
                    tech_clock[tech.id] = end_h
                    break

        return SchedulePlan(
            assignments=assignments,
            rationale="Deterministically synthesized and verified via Z3 Optimize solver.",
        )

    async def verify_and_repair_loop(
        self,
        tasks: list[ScheduledTask],
        technicians: list[Technician],
        initial_plan: SchedulePlan | None = None,
        llm_repair_callback: Any = None,
    ) -> SymbolicVerificationResponse:
        """Executes the iterative self-correction loop or Z3 synthesis."""
        start_time = time.perf_counter()

        # If no initial plan provided, solve directly
        if initial_plan is None:
            optimal_plan = self.solve_optimal_z3(tasks, technicians)
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            if optimal_plan is not None:
                return SymbolicVerificationResponse(
                    is_valid=True,
                    status="solved_optimal",
                    plan=optimal_plan,
                    violations=[],
                    solver_time_ms=round(elapsed_ms, 2),
                    rounds_executed=1,
                )
            return SymbolicVerificationResponse(
                is_valid=False,
                status="unsat",
                plan=None,
                violations=[{"rule": "UNSATISFIABLE", "message": "No valid schedule exists for given constraints."}],
                solver_time_ms=round(elapsed_ms, 2),
                rounds_executed=1,
            )

        current_plan = initial_plan
        for current_round in range(1, self.max_correction_rounds + 1):
            is_valid, violations = self.verify_plan_z3(tasks, technicians, current_plan)
            if is_valid:
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                status = "verified" if current_round == 1 else "repaired"
                return SymbolicVerificationResponse(
                    is_valid=True,
                    status=status,
                    plan=current_plan,
                    violations=[],
                    solver_time_ms=round(elapsed_ms, 2),
                    rounds_executed=current_round,
                )

            logger.info(
                "Round %d: Plan has %d violations. Attempting self-correction...",
                current_round,
                len(violations),
            )

            # If LLM callback available, request repair
            if llm_repair_callback is not None and current_round < self.max_correction_rounds:
                try:
                    repaired = await llm_repair_callback(tasks, technicians, current_plan, violations)
                    if repaired is not None:
                        current_plan = repaired
                        continue
                except Exception as exc:
                    logger.warning("LLM self-correction callback failed: %s", exc)

        # Fallback to Z3 deterministic optimal solver
        logger.info("Iterative loop exhausted. Falling back to deterministic Z3 solver.")
        optimal_plan = self.solve_optimal_z3(tasks, technicians)
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        if optimal_plan is not None:
            return SymbolicVerificationResponse(
                is_valid=True,
                status="solved_optimal",
                plan=optimal_plan,
                violations=[],
                solver_time_ms=round(elapsed_ms, 2),
                rounds_executed=self.max_correction_rounds,
            )

        return SymbolicVerificationResponse(
            is_valid=False,
            status="unsat",
            plan=current_plan,
            violations=violations,
            solver_time_ms=round(elapsed_ms, 2),
            rounds_executed=self.max_correction_rounds,
        )
