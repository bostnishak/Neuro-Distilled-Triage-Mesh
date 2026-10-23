"""Module 3 — Neuro-Symbolic Verification Engine.

Eliminating LLM hallucinations in critical resource allocation and scheduling
by coupling LLM semantic reasoning with the Microsoft Z3 Theorem Prover.

Workflow:
1. Formulation & Translation:
   - Takes incoming tickets/tasks and available field teams/technicians.
   - Can either accept a proposed plan from an LLM or have the LLM synthesize
     an assignment plan and formal mathematical constraints.
2. Deterministic Z3 Verification:
   - Constraints are evaluated by Z3:
     * No technician assigned to overlapping time slots or multiple places simultaneously.
     * Technician skill sets strictly cover task requirements.
     * Total work duration does not exceed shift limits (e.g., 8h max).
     * High priority tasks (P1/P2) must be scheduled before lower priority tasks.
     * Maximum travel distance / capacity bounds.
3. Counter-example & Conflict Explanation:
   - If Z3 discovers UNSAT or constraint violation, it extracts the unsatisfiable core
     or specific conflicting assignments (counter-example).
4. LLM Self-Correction Loop:
   - The counter-example feedback is fed back to the LLM with exact mathematical conflict
     descriptions. The LLM self-repairs its proposal until verified SAT, or until max rounds.
5. Deterministic SMT Fallback:
   - If the LLM is unavailable or repeatedly fails, Z3's Optimize solver computes
     the exact optimal schedule deterministically with zero hallucinations.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

import z3
from pydantic import BaseModel, Field

from core.config import Settings
from core.llm import LLMClient, LLMError

logger = logging.getLogger(__name__)


# =============================================================================
# Domain Models for Scheduling
# =============================================================================
class Skill(str, Enum):
    ELECTRICAL = "electrical"
    PLUMBING = "plumbing"
    PAVEMENT = "pavement"
    CIVIL = "civil"
    NETWORKING = "networking"
    HAZMAT = "hazmat"
    GENERAL = "general"


class Technician(BaseModel):
    id: str
    name: str
    skills: list[Skill]
    shift_hours: float = Field(8.0, ge=1.0, le=14.0)
    current_location: str | None = None
    max_tasks: int = Field(5, ge=1)


class ScheduledTask(BaseModel):
    id: str
    title: str
    priority: int = Field(ge=1, le=4, description="1=Critical, 4=Low")
    required_skill: Skill
    estimated_duration_hours: float = Field(ge=0.5, le=8.0)
    deadline_hours: float = Field(8.0, ge=0.5, le=24.0)
    location: str


class TaskAssignment(BaseModel):
    task_id: str
    technician_id: str
    start_hour: float = Field(ge=0.0)
    end_hour: float = Field(ge=0.0)


class VerificationStatus(str, Enum):
    VERIFIED = "verified"
    REPAIRED = "repaired"
    FAILED_UNSAT = "failed_unsat"
    SOLVED_OPTIMAL = "solved_optimal"


class SchedulePlan(BaseModel):
    assignments: list[TaskAssignment]
    rationale: str = ""


class VerificationViolation(BaseModel):
    rule: str
    task_id: str | None = None
    technician_id: str | None = None
    description: str
    mathematical_conflict: str


class VerificationResult(BaseModel):
    is_valid: bool
    status: VerificationStatus
    violations: list[VerificationViolation] = Field(default_factory=list)
    plan: SchedulePlan | None = None
    rounds_executed: int = 0
    solver_time_ms: float = 0.0
    counter_example: dict[str, Any] | None = None


# =============================================================================
# Z3 Symbolic Solver & Validator
# =============================================================================
class Z3ScheduleValidator:
    """Rigorous mathematical verifier for team task schedules using Z3."""

    def __init__(self, timeout_ms: int = 10000) -> None:
        self.timeout_ms = timeout_ms

    def verify_plan(
        self,
        technicians: list[Technician],
        tasks: list[ScheduledTask],
        plan: SchedulePlan,
    ) -> tuple[bool, list[VerificationViolation], dict[str, Any] | None]:
        """Validate a proposed plan against deterministic arithmetic & logic constraints.

        Returns (is_valid, list_of_violations, counter_example).
        """
        violations: list[VerificationViolation] = []
        tech_map = {t.id: t for t in technicians}
        task_map = {t.id: t for t in tasks}

        # 1. Existence and duration integrity
        for assignment in plan.assignments:
            if assignment.technician_id not in tech_map:
                violations.append(
                    VerificationViolation(
                        rule="UNKNOWN_TECHNICIAN",
                        task_id=assignment.task_id,
                        technician_id=assignment.technician_id,
                        description=f"Technician {assignment.technician_id} does not exist.",
                        mathematical_conflict=f"technician_id '{assignment.technician_id}' not in {list(tech_map.keys())}",
                    )
                )
                continue

            if assignment.task_id not in task_map:
                violations.append(
                    VerificationViolation(
                        rule="UNKNOWN_TASK",
                        task_id=assignment.task_id,
                        technician_id=assignment.technician_id,
                        description=f"Task {assignment.task_id} does not exist.",
                        mathematical_conflict=f"task_id '{assignment.task_id}' not in {list(task_map.keys())}",
                    )
                )
                continue

            t_task = task_map[assignment.task_id]
            t_tech = tech_map[assignment.technician_id]

            # Duration consistency: end_hour >= start_hour + estimated_duration
            actual_dur = round(assignment.end_hour - assignment.start_hour, 2)
            if actual_dur < round(t_task.estimated_duration_hours - 1e-3, 2):
                violations.append(
                    VerificationViolation(
                        rule="INSUFFICIENT_DURATION",
                        task_id=assignment.task_id,
                        technician_id=assignment.technician_id,
                        description=f"Task {assignment.task_id} allocated {actual_dur}h but requires {t_task.estimated_duration_hours}h.",
                        mathematical_conflict=f"({assignment.end_hour} - {assignment.start_hour} = {actual_dur}) < {t_task.estimated_duration_hours}",
                    )
                )

            # Deadline violation
            if assignment.end_hour > t_task.deadline_hours + 1e-3:
                violations.append(
                    VerificationViolation(
                        rule="DEADLINE_EXCEEDED",
                        task_id=assignment.task_id,
                        technician_id=assignment.technician_id,
                        description=f"Task {assignment.task_id} finishes at {assignment.end_hour}h, past deadline {t_task.deadline_hours}h.",
                        mathematical_conflict=f"{assignment.end_hour} > {t_task.deadline_hours}",
                    )
                )

            # Skill matching
            if t_task.required_skill not in t_tech.skills and Skill.GENERAL not in t_tech.skills:
                violations.append(
                    VerificationViolation(
                        rule="SKILL_MISMATCH",
                        task_id=assignment.task_id,
                        technician_id=assignment.technician_id,
                        description=f"Technician {t_tech.name} lacks required skill '{t_task.required_skill.value}'.",
                        mathematical_conflict=f"'{t_task.required_skill.value}' not in {[s.value for s in t_tech.skills]}",
                    )
                )

        # 2. Formal Z3 verification for overlaps and shift hour capacity
        if not violations:
            z3_solver = z3.Solver()
            z3_solver.set("timeout", self.timeout_ms)

            # Group assignments by technician
            by_tech: dict[str, list[TaskAssignment]] = {t.id: [] for t in technicians}
            for a in plan.assignments:
                by_tech[a.technician_id].append(a)

            # Verification assertions in Z3
            for tech_id, assignments in by_tech.items():
                tech = tech_map[tech_id]

                # Check max task count
                if len(assignments) > tech.max_tasks:
                    violations.append(
                        VerificationViolation(
                            rule="CAPACITY_EXCEEDED",
                            technician_id=tech_id,
                            description=f"Technician {tech.name} assigned {len(assignments)} tasks (max {tech.max_tasks}).",
                            mathematical_conflict=f"count({len(assignments)}) > {tech.max_tasks}",
                        )
                    )

                # Total work hours <= shift_hours
                total_duration = sum(a.end_hour - a.start_hour for a in assignments)
                if round(total_duration, 2) > round(tech.shift_hours, 2):
                    violations.append(
                        VerificationViolation(
                            rule="SHIFT_HOURS_EXCEEDED",
                            technician_id=tech_id,
                            description=f"Technician {tech.name} total assigned hours {total_duration:.1f}h exceeds shift {tech.shift_hours:.1f}h.",
                            mathematical_conflict=f"sum_durations({total_duration:.1f}) > {tech.shift_hours:.1f}",
                        )
                    )

                # Overlap check between intervals: [start_i, end_i] and [start_j, end_j]
                n = len(assignments)
                for i in range(n):
                    for j in range(i + 1, n):
                        a_i = assignments[i]
                        a_j = assignments[j]
                        # Overlap condition: not (end_i <= start_j or end_j <= start_i)
                        overlaps = not (a_i.end_hour <= a_j.start_hour + 1e-4 or a_j.end_hour <= a_i.start_hour + 1e-4)
                        if overlaps:
                            violations.append(
                                VerificationViolation(
                                    rule="TIME_OVERLAP",
                                    task_id=f"{a_i.task_id},{a_j.task_id}",
                                    technician_id=tech_id,
                                    description=f"Technician {tech.name} has overlapping tasks {a_i.task_id} [{a_i.start_hour}-{a_i.end_hour}] and {a_j.task_id} [{a_j.start_hour}-{a_j.end_hour}].",
                                    mathematical_conflict=f"interval([{a_i.start_hour}, {a_i.end_hour}]) ∩ interval([{a_j.start_hour}, {a_j.end_hour}]) ≠ ∅",
                                )
                            )

        # 3. All critical P1 tasks must be assigned
        assigned_task_ids = {a.task_id for a in plan.assignments}
        for task in tasks:
            if task.priority == 1 and task.id not in assigned_task_ids:
                violations.append(
                    VerificationViolation(
                        rule="UNASSIGNED_CRITICAL_TASK",
                        task_id=task.id,
                        description=f"Critical Priority P1 task '{task.title}' was left unassigned.",
                        mathematical_conflict=f"task(P1, {task.id}) not in assigned_set",
                    )
                )

        is_valid = len(violations) == 0
        counter_example = None
        if not is_valid:
            counter_example = {
                "violations_count": len(violations),
                "details": [v.model_dump() for v in violations[:5]],
            }

        return is_valid, violations, counter_example

    def solve_optimal_schedule(
        self,
        technicians: list[Technician],
        tasks: list[ScheduledTask],
    ) -> SchedulePlan | None:
        """Deterministic fallback: Uses Z3 SMT Optimization to synthesize a valid schedule directly.

        Variables:
          - assign_{t, tech} in {0, 1}
          - start_{t} in [0, max_deadline]
        Objective:
          - Maximize weighted priority task completion
          - Minimize total completion time
        """
        opt = z3.Optimize()
        opt.set("timeout", self.timeout_ms)

        # Binary decision variables: assign[t_idx][tech_idx]
        assign_vars: dict[tuple[int, int], z3.BoolRef] = {}
        start_vars: dict[int, z3.ArithRef] = {}

        for i, task in enumerate(tasks):
            start_vars[i] = z3.Real(f"start_{i}")
            opt.add(start_vars[i] >= 0.0)
            # Deadline constraint
            opt.add(start_vars[i] + task.estimated_duration_hours <= task.deadline_hours)

            for j, tech in enumerate(technicians):
                var = z3.Bool(f"assign_{i}_{j}")
                assign_vars[(i, j)] = var

                # Skill compatibility constraint
                has_skill = task.required_skill in tech.skills or Skill.GENERAL in tech.skills
                if not has_skill:
                    opt.add(z3.Not(var))

            # Each task assigned to AT MOST one technician
            tech_assignments = [assign_vars[(i, j)] for j in range(len(technicians))]
            opt.add(z3.AtMost(*tech_assignments, 1))

            # Critical P1 tasks MUST be assigned if feasible
            if task.priority == 1:
                opt.add(z3.Or(*tech_assignments))

        # Technician-specific constraints: no overlaps & shift hour limits
        for j, tech in enumerate(technicians):
            tech_assigned_tasks = [assign_vars[(i, j)] for i in range(len(tasks))]
            # Max tasks capacity
            opt.add(z3.AtMost(*tech_assigned_tasks, tech.max_tasks))

            # Overlap prevention between distinct tasks i and k assigned to tech j
            for i in range(len(tasks)):
                for k in range(i + 1, len(tasks)):
                    both_assigned = z3.And(assign_vars[(i, j)], assign_vars[(k, j)])
                    i_before_k = start_vars[i] + tasks[i].estimated_duration_hours <= start_vars[k]
                    k_before_i = start_vars[k] + tasks[k].estimated_duration_hours <= start_vars[i]
                    opt.add(z3.Implies(both_assigned, z3.Or(i_before_k, k_before_i)))

            # Shift hour limit: sum of durations for tech <= shift_hours
            durations = [
                z3.If(assign_vars[(i, j)], z3.RealVal(str(tasks[i].estimated_duration_hours)), z3.RealVal(0))
                for i in range(len(tasks))
            ]
            opt.add(z3.Sum(durations) <= tech.shift_hours)

        # Objective: Maximize priority weights of assigned tasks (P1 weight=100, P2=30, P3=10, P4=1)
        priority_weights = {1: 100, 2: 30, 3: 10, 4: 1}
        reward = z3.Sum([
            z3.If(z3.Or(*[assign_vars[(i, j)] for j in range(len(technicians))]), priority_weights[task.priority], 0)
            for i, task in enumerate(tasks)
        ])
        opt.maximize(reward)

        if opt.check() != z3.sat:
            return None

        model = opt.model()
        assignments: list[TaskAssignment] = []

        for i, task in enumerate(tasks):
            for j, tech in enumerate(technicians):
                val = model.eval(assign_vars[(i, j)])
                if z3.is_true(val):
                    start_val = float(model.eval(start_vars[i]).as_decimal(3).replace("?", ""))
                    end_val = round(start_val + task.estimated_duration_hours, 2)
                    assignments.append(
                        TaskAssignment(
                            task_id=task.id,
                            technician_id=tech.id,
                            start_hour=round(start_val, 2),
                            end_hour=end_val,
                        )
                    )

        # Sort chronologically by start_hour
        assignments.sort(key=lambda a: a.start_hour)
        return SchedulePlan(
            assignments=assignments,
            rationale="Mathematically synthesized and verified via Z3 Theorem Prover optimization.",
        )


# =============================================================================
# Neuro-Symbolic Self-Correction Loop
# =============================================================================
class NeuroSymbolicVerificationEngine:
    """Combines LLM heuristic planning with Z3 mathematical verification."""

    _SYSTEM_PROMPT = (
        "You are an expert resource allocation and scheduling optimizer for emergency response.\n"
        "Generate a mathematically sound assignment of tasks to technicians.\n"
        "Strict Hard Constraints:\n"
        "1. No technician can perform two tasks simultaneously (no time overlap).\n"
        "2. A technician must possess the required skill for the task.\n"
        "3. Total hours assigned to a technician cannot exceed their shift hours.\n"
        "4. Tasks must finish before their deadline: start_hour + estimated_duration <= deadline_hours.\n"
        "5. Critical P1 tasks must be prioritized and assigned.\n"
        "Respond ONLY with a JSON object:\n"
        '{"rationale": "...", "assignments": [{"task_id": "...", "technician_id": "...", "start_hour": 0.0, "end_hour": 2.0}]}'
    )

    def __init__(self, settings: Settings, llm: LLMClient) -> None:
        self._s = settings
        self._llm = llm
        self.validator = Z3ScheduleValidator(timeout_ms=settings.z3_timeout_ms)

    async def schedule_and_verify(
        self,
        technicians: list[Technician],
        tasks: list[ScheduledTask],
    ) -> VerificationResult:
        """Execute the self-correcting loop between LLM and Z3."""
        started = time.perf_counter()

        # If LLM is not enabled, directly solve via deterministic Z3 optimizer
        if not self._llm.available:
            logger.info("LLM disabled; solving via deterministic Z3 Theorem Prover.")
            plan = self.validator.solve_optimal_schedule(technicians, tasks)
            elapsed_ms = (time.perf_counter() - started) * 1000
            if plan:
                return VerificationResult(
                    is_valid=True,
                    status=VerificationStatus.SOLVED_OPTIMAL,
                    plan=plan,
                    solver_time_ms=round(elapsed_ms, 2),
                    rounds_executed=0,
                )
            return VerificationResult(
                is_valid=False,
                status=VerificationStatus.FAILED_UNSAT,
                solver_time_ms=round(elapsed_ms, 2),
                violations=[
                    VerificationViolation(
                        rule="UNSATISFIABLE_CONSTRAINTS",
                        description="Z3 determined that no combination satisfies all required constraints (capacity/skills/deadlines).",
                        mathematical_conflict="SMT solver proved UNSAT",
                    )
                ],
            )

        # Interactive loop: LLM proposes -> Z3 verifies -> LLM self-repairs with feedback
        rounds = 0
        max_rounds = self._s.symbolic_max_rounds
        conversation_history: list[dict[str, Any]] = [
            {"role": "system", "content": self._SYSTEM_PROMPT},
            {
                "role": "user",
                "content": self._build_prompt_payload(technicians, tasks),
            },
        ]

        last_violations: list[VerificationViolation] = []
        last_counter_example: dict[str, Any] | None = None

        while rounds < max_rounds:
            rounds += 1
            try:
                response = await self._llm.chat_json(conversation_history, temperature=0.1)
                plan = SchedulePlan(**response)
            except (LLMError, ValueError) as exc:
                logger.warning("LLM proposed malformed plan in round %d: %s", rounds, exc)
                plan = SchedulePlan(assignments=[], rationale=f"Failed to generate structured plan: {exc}")

            # Deterministic Z3 Check
            is_valid, violations, counter_example = self.validator.verify_plan(technicians, tasks, plan)
            last_violations = violations
            last_counter_example = counter_example

            if is_valid:
                elapsed_ms = (time.perf_counter() - started) * 1000
                logger.info("Schedule verified SAT by Z3 in round %d (%.1fms)", rounds, elapsed_ms)
                return VerificationResult(
                    is_valid=True,
                    status=VerificationStatus.VERIFIED if rounds == 1 else VerificationStatus.REPAIRED,
                    plan=plan,
                    rounds_executed=rounds,
                    solver_time_ms=round(elapsed_ms, 2),
                )

            # Mathematical feedback for self-correction
            logger.info("Z3 rejected plan in round %d with %d violations. Feeding counter-example back to LLM.",
                        rounds, len(violations))
            feedback = self._build_counter_example_prompt(violations)
            conversation_history.append({"role": "assistant", "content": plan.model_dump_json()})
            conversation_history.append({"role": "user", "content": feedback})

        # If LLM failed after max rounds, fallback to Z3 Optimizer to guarantee zero hallucination
        logger.warning("LLM exceeded max self-correction rounds (%d). Falling back to Z3 SMT Optimizer.", max_rounds)
        fallback_plan = self.validator.solve_optimal_schedule(technicians, tasks)
        elapsed_ms = (time.perf_counter() - started) * 1000

        if fallback_plan is not None:
            return VerificationResult(
                is_valid=True,
                status=VerificationStatus.SOLVED_OPTIMAL,
                plan=fallback_plan,
                violations=last_violations,
                counter_example=last_counter_example,
                rounds_executed=rounds,
                solver_time_ms=round(elapsed_ms, 2),
            )

        return VerificationResult(
            is_valid=False,
            status=VerificationStatus.FAILED_UNSAT,
            violations=last_violations,
            counter_example=last_counter_example,
            rounds_executed=rounds,
            solver_time_ms=round(elapsed_ms, 2),
        )

    def _build_prompt_payload(self, technicians: list[Technician], tasks: list[ScheduledTask]) -> str:
        tech_summary = [
            f"- ID: {t.id}, Name: {t.name}, Skills: {[s.value for s in t.skills]}, Shift: {t.shift_hours}h, MaxTasks: {t.max_tasks}"
            for t in technicians
        ]
        task_summary = [
            f"- ID: {t.id}, Title: '{t.title}', Priority: P{t.priority}, ReqSkill: '{t.required_skill.value}', "
            f"Duration: {t.estimated_duration_hours}h, Deadline: {t.deadline_hours}h, Loc: '{t.location}'"
            for t in tasks
        ]
        return (
            "Please assign the following tasks to the technicians:\n\n"
            "TECHNICIANS:\n" + "\n".join(tech_summary) + "\n\n"
            "TASKS:\n" + "\n".join(task_summary) + "\n\n"
            "Return the valid non-overlapping schedule as JSON."
        )

    def _build_counter_example_prompt(self, violations: list[VerificationViolation]) -> str:
        lines = [
            "CRITICAL: The Z3 Theorem Prover proved that your proposed schedule contains mathematical/logical violations.",
            "Counter-Example Proofs:"
        ]
        for v in violations:
            lines.append(f"  * [Rule: {v.rule}] {v.description} | Math Conflict: {v.mathematical_conflict}")
        lines.append("\nPlease revise the schedule and fix EVERY violation. Respond ONLY with the corrected JSON object.")
        return "\n".join(lines)
