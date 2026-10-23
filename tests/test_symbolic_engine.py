"""Unit tests for Module 3: Neuro-Symbolic Verification Engine (Z3)."""
import pytest
from services.symbolic_engine import (
    NeuroSymbolicVerificationEngine,
    SchedulePlan,
    ScheduledTask,
    Skill,
    TaskAssignment,
    Technician,
    VerificationStatus,
    Z3ScheduleValidator,
)


@pytest.fixture
def sample_technicians():
    return [
        Technician(
            id="tech-alice",
            name="Alice",
            skills=[Skill.ELECTRICAL],
            shift_hours=8.0,
            max_tasks=4,
        ),
        Technician(
            id="tech-bob",
            name="Bob",
            skills=[Skill.PLUMBING],
            shift_hours=8.0,
            max_tasks=4,
        ),
    ]


@pytest.fixture
def sample_tasks():
    return [
        ScheduledTask(
            id="task-transformer",
            title="Transformer Sparking",
            priority=1,
            required_skill=Skill.ELECTRICAL,
            estimated_duration_hours=2.0,
            deadline_hours=4.0,
            location="Downtown",
        ),
        ScheduledTask(
            id="task-water-leak",
            title="Main Burst",
            priority=1,
            required_skill=Skill.PLUMBING,
            estimated_duration_hours=3.0,
            deadline_hours=6.0,
            location="Uptown",
        ),
        ScheduledTask(
            id="task-pole",
            title="Pole Inspection",
            priority=3,
            required_skill=Skill.ELECTRICAL,
            estimated_duration_hours=1.5,
            deadline_hours=8.0,
            location="Suburbs",
        ),
    ]


def test_z3_detects_skill_mismatch(sample_technicians, sample_tasks):
    validator = Z3ScheduleValidator()
    # Assign plumbing task to electrical technician Alice
    invalid_plan = SchedulePlan(
        assignments=[
            TaskAssignment(task_id="task-transformer", technician_id="tech-alice", start_hour=0.0, end_hour=2.0),
            TaskAssignment(task_id="task-water-leak", technician_id="tech-alice", start_hour=2.0, end_hour=5.0),
        ]
    )
    is_valid, violations, _ = validator.verify_plan(sample_technicians, sample_tasks, invalid_plan)
    assert not is_valid
    assert any(v.rule == "SKILL_MISMATCH" for v in violations)


def test_z3_detects_time_overlap(sample_technicians, sample_tasks):
    validator = Z3ScheduleValidator()
    # Alice assigned two electrical tasks overlapping at [1.0 - 2.0]
    overlapping_plan = SchedulePlan(
        assignments=[
            TaskAssignment(task_id="task-transformer", technician_id="tech-alice", start_hour=0.0, end_hour=2.0),
            TaskAssignment(task_id="task-pole", technician_id="tech-alice", start_hour=1.0, end_hour=2.5),
            TaskAssignment(task_id="task-water-leak", technician_id="tech-bob", start_hour=0.0, end_hour=3.0),
        ]
    )
    is_valid, violations, _ = validator.verify_plan(sample_technicians, sample_tasks, overlapping_plan)
    assert not is_valid
    assert any(v.rule == "TIME_OVERLAP" for v in violations)


def test_z3_detects_exceeded_shift_hours(sample_technicians, sample_tasks):
    validator = Z3ScheduleValidator()
    # Shift limit is 8.0, assignment totals 9.0h
    plan = SchedulePlan(
        assignments=[
            TaskAssignment(task_id="task-transformer", technician_id="tech-alice", start_hour=0.0, end_hour=5.0),
            TaskAssignment(task_id="task-pole", technician_id="tech-alice", start_hour=5.0, end_hour=9.0),
            TaskAssignment(task_id="task-water-leak", technician_id="tech-bob", start_hour=0.0, end_hour=3.0),
        ]
    )
    is_valid, violations, _ = validator.verify_plan(sample_technicians, sample_tasks, plan)
    assert not is_valid
    assert any(v.rule == "SHIFT_HOURS_EXCEEDED" for v in violations)


def test_z3_detects_unassigned_critical_task(sample_technicians, sample_tasks):
    validator = Z3ScheduleValidator()
    # Task 'task-water-leak' is P1 critical but left unassigned
    plan = SchedulePlan(
        assignments=[
            TaskAssignment(task_id="task-transformer", technician_id="tech-alice", start_hour=0.0, end_hour=2.0),
            TaskAssignment(task_id="task-pole", technician_id="tech-alice", start_hour=2.0, end_hour=3.5),
        ]
    )
    is_valid, violations, _ = validator.verify_plan(sample_technicians, sample_tasks, plan)
    assert not is_valid
    assert any(v.rule == "UNASSIGNED_CRITICAL_TASK" for v in violations)


def test_z3_deterministic_optimal_synthesis(sample_technicians, sample_tasks):
    validator = Z3ScheduleValidator()
    plan = validator.solve_optimal_schedule(sample_technicians, sample_tasks)
    assert plan is not None
    assert len(plan.assignments) >= 2

    # Verify that the synthesized plan satisfies all constraints
    is_valid, violations, _ = validator.verify_plan(sample_technicians, sample_tasks, plan)
    assert is_valid
    assert len(violations) == 0
