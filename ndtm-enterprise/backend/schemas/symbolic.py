"""Neuro-Symbolic Z3 Theorem Prover contract schemas."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class FieldTeamDTO(BaseModel):
    id: UUID
    team_code: str
    skills: list[str]
    shift_remaining_minutes: int = Field(..., ge=0)
    max_concurrent_tasks: int = Field(default=2, ge=1)
    latitude: float
    longitude: float
    is_available: bool = True


class IncidentTaskDTO(BaseModel):
    id: UUID
    category: str
    urgency_score: int = Field(..., ge=1, le=10)
    required_skills: list[str]
    estimated_work_minutes: int = Field(default=60, ge=15, le=360)
    latitude: float
    longitude: float


class TaskAssignmentDTO(BaseModel):
    incident_id: UUID
    team_id: UUID
    estimated_travel_minutes: int
    estimated_work_minutes: int
    arrival_time_minutes: int


class Z3SolveRequest(BaseModel):
    incidents: list[IncidentTaskDTO] = Field(default_factory=list)
    teams: list[FieldTeamDTO] = Field(default_factory=list)
    initial_proposal: list[TaskAssignmentDTO] | None = None


class IterationAuditLog(BaseModel):
    iteration: int
    status: str  # UNSAT | SAT
    unsat_core_conflicts: list[str] = Field(default_factory=list)
    proposal: list[TaskAssignmentDTO] = Field(default_factory=list)


class Z3SolveResponse(BaseModel):
    is_sat: bool
    status: str  # VERIFIED | REPAIRED | Z3_OPTIMIZED | UNSAT_FATAL
    assignments: list[TaskAssignmentDTO] = Field(default_factory=list)
    unsat_core_conflicts: list[str] = Field(default_factory=list)
    iteration_history: list[IterationAuditLog] = Field(default_factory=list)
    iterations_executed: int
    z3_proof_smt2: str
    solver_time_ms: float
