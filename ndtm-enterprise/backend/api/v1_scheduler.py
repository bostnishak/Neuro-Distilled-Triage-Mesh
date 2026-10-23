"""Neuro-Symbolic Z3 Scheduling REST router."""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user, get_db
from backend.db.models import User
from backend.db.repositories import DispatchScheduleRepository, FieldTeamRepository
from backend.schemas.symbolic import (
    FieldTeamDTO,
    TaskAssignmentDTO,
    Z3SolveRequest,
    Z3SolveResponse,
)
from backend.services.websocket_manager import ws_manager
from backend.services.z3_symbolic_solver import NeuroSymbolicZ3Solver

logger = logging.getLogger("api.scheduler")
router = APIRouter(prefix="/scheduler", tags=["Neuro-Symbolic Scheduler"])

z3_solver = NeuroSymbolicZ3Solver(max_iterations=3)


@router.get("/teams", response_model=list[FieldTeamDTO])
async def list_available_teams(
    session: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user),
) -> list[FieldTeamDTO]:
    """Retrieves all registered field teams and their remaining shift capacities."""
    teams = await FieldTeamRepository.get_available_teams(session)
    return [
        FieldTeamDTO(
            id=t.id,
            team_code=t.team_code,
            skills=t.skills,
            shift_remaining_minutes=t.shift_remaining_minutes,
            max_concurrent_tasks=t.max_concurrent_tasks,
            latitude=39.9208,  # Default Ankara base
            longitude=32.8543,
            is_available=t.is_available,
        )
        for t in teams
    ]


@router.post("/solve", response_model=Z3SolveResponse)
async def solve_and_verify_schedule(
    req: Z3SolveRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user),
) -> Z3SolveResponse:
    """Formally verifies scheduling plans and extracts unsat_core or executes optimal Z3 synthesis."""
    if not req.incidents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incident task roster must not be empty.",
        )

    # Fetch registered teams if not provided in payload
    teams = req.teams
    if not teams:
        db_teams = await FieldTeamRepository.get_available_teams(session)
        teams = [
            FieldTeamDTO(
                id=t.id,
                team_code=t.team_code,
                skills=t.skills,
                shift_remaining_minutes=t.shift_remaining_minutes,
                max_concurrent_tasks=t.max_concurrent_tasks,
                latitude=39.9208,
                longitude=32.8543,
                is_available=t.is_available,
            )
            for t in db_teams
        ]

    # Execute Neuro-Symbolic Z3 Solver with unsat_core self-correction loop
    result = z3_solver.execute_self_correcting_loop(
        incidents=req.incidents,
        teams=teams,
        initial_proposal=req.initial_proposal,
    )

    # If SAT, persist verified assignments
    if result.is_sat:
        for assignment in result.assignments:
            await DispatchScheduleRepository.save_schedule(
                session=session,
                incident_id=assignment.incident_id,
                team_id=assignment.team_id,
                travel_min=assignment.estimated_travel_minutes,
                work_min=assignment.estimated_work_minutes,
                z3_proof_smt2=result.z3_proof_smt2[:2000],  # Save initial proof assertions
                iterations=result.iterations_executed,
            )
        await session.commit()
        logger.info("Persisted %d verified dispatch assignments to database.", len(result.assignments))

    # Broadcast Z3 schedule resolution event to WebSocket cockpit
    await ws_manager.broadcast_event(
        "z3_schedule_solved",
        {
            "status": result.status,
            "is_sat": result.is_sat,
            "assignments_count": len(result.assignments),
            "iterations": result.iterations_executed,
            "solver_time_ms": result.solver_time_ms,
            "conflicts_count": len(result.unsat_core_conflicts),
        },
    )

    return result
