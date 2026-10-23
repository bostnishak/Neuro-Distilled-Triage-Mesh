"""Unit tests for Neuro-Symbolic Verification Engine (Microsoft Z3 SMT Prover)."""
from __future__ import annotations

import pytest

from ndtm_platform.models.schemas import (
    SchedulePlan,
    ScheduledTask,
    Skill,
    TaskAssignment,
    Technician,
)
from ndtm_platform.services.symbolic_engine import NeuroSymbolicEngine


@pytest.fixture
def sample_technicians():
    return [
        Technician(id="tech_1", name="Ali Vural", skills=[Skill.PLUMBING], shift_hours=8.0),
        Technician(id="tech_2", name="Canan Demir", skills=[Skill.ELECTRICAL, Skill.NETWORKING], shift_hours=8.0),
    ]


@pytest.fixture
def sample_tasks():
    return [
        ScheduledTask(
            id="task_1",
            title="Ana vana su patlağı",
            priority=1,
            required_skill=Skill.PLUMBING,
            estimated_duration_hours=2.0,
            deadline_hours=6.0,
            location="Kızılay Meydanı",
        ),
        ScheduledTask(
            id="task_2",
            title="Sokak trafo arızası",
            priority=2,
            required_skill=Skill.ELECTRICAL,
            estimated_duration_hours=3.0,
            deadline_hours=8.0,
            location="Tunalı Hilmi Cd.",
        ),
    ]


def test_z3_verification_valid_plan(sample_tasks, sample_technicians):
    engine = NeuroSymbolicEngine()
    plan = SchedulePlan(
        assignments=[
            TaskAssignment(task_id="task_1", technician_id="tech_1", start_hour=1.0, end_hour=3.0),
            TaskAssignment(task_id="task_2", technician_id="tech_2", start_hour=1.0, end_hour=4.0),
        ]
    )

    is_valid, violations = engine.verify_plan_z3(sample_tasks, sample_technicians, plan)
    assert is_valid is True
    assert len(violations) == 0


def test_z3_detects_skill_mismatch(sample_tasks, sample_technicians):
    engine = NeuroSymbolicEngine()
    # Assigning plumbing task to tech_2 who only has electrical/networking
    plan = SchedulePlan(
        assignments=[
            TaskAssignment(task_id="task_1", technician_id="tech_2", start_hour=1.0, end_hour=3.0),
            TaskAssignment(task_id="task_2", technician_id="tech_2", start_hour=4.0, end_hour=7.0),
        ]
    )

    is_valid, violations = engine.verify_plan_z3(sample_tasks, sample_technicians, plan)
    assert is_valid is False
    rules = [v["rule"] for v in violations]
    assert "SKILL_MISMATCH" in rules


def test_z3_detects_interval_overlap(sample_tasks, sample_technicians):
    engine = NeuroSymbolicEngine()
    # Add another task for tech_2
    tasks = sample_tasks + [
        ScheduledTask(
            id="task_3",
            title="Fiber optik onarımı",
            priority=3,
            required_skill=Skill.NETWORKING,
            estimated_duration_hours=2.0,
            deadline_hours=8.0,
            location="Balgat",
        )
    ]
    # Tech 2 scheduled simultaneously on task 2 and task 3
    plan = SchedulePlan(
        assignments=[
            TaskAssignment(task_id="task_1", technician_id="tech_1", start_hour=1.0, end_hour=3.0),
            TaskAssignment(task_id="task_2", technician_id="tech_2", start_hour=2.0, end_hour=5.0),
            TaskAssignment(task_id="task_3", technician_id="tech_2", start_hour=3.0, end_hour=5.0),  # Overlaps!
        ]
    )

    is_valid, violations = engine.verify_plan_z3(tasks, sample_technicians, plan)
    assert is_valid is False
    rules = [v["rule"] for v in violations]
    assert "INTERVAL_OVERLAP" in rules


def test_z3_optimal_schedule_synthesis(sample_tasks, sample_technicians):
    engine = NeuroSymbolicEngine()
    optimal_plan = engine.solve_optimal_z3(sample_tasks, sample_technicians)

    assert optimal_plan is not None
    assert len(optimal_plan.assignments) == 2
    is_valid, violations = engine.verify_plan_z3(sample_tasks, sample_technicians, optimal_plan)
    assert is_valid is True
    assert len(violations) == 0
