import datetime
import uuid
from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from infrastructure.database.connection import get_db
from infrastructure.repositories.uow_repositories import UnitOfWork
from infrastructure.database.orm_models import FieldTeamOrm, IncidentOrm, DispatchScheduleOrm, UserOrm
from presentation.api.dependencies import get_current_user
from domain.services.smt_pareto_dispatcher import SmtParetoDispatcher
from domain.entities import IncidentEntity, FieldTeamEntity
from domain.value_objects import GeoCoordinates
from domain.events import SmtDispatchOptimizedEvent

router = APIRouter(prefix="/dispatch", tags=["Formal MaxSMT Resource Dispatch"])
_dispatcher = SmtParetoDispatcher()


@router.get("/teams")
async def list_field_teams(
    current_user: UserOrm = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> List[Dict[str, Any]]:
    """Lists rapid response field units with operational readiness and burnout status."""
    stmt = select(
        FieldTeamOrm.id,
        FieldTeamOrm.team_name,
        FieldTeamOrm.specialization,
        FieldTeamOrm.status,
        FieldTeamOrm.shift_start_hour,
        FieldTeamOrm.shift_end_hour,
        FieldTeamOrm.burnout_index,
        FieldTeamOrm.cumulative_shifts_week,
        func.ST_X(FieldTeamOrm.current_location).label("lon"),
        func.ST_Y(FieldTeamOrm.current_location).label("lat"),
    )
    res = await session.execute(stmt)
    rows = res.fetchall()

    return [
        {
            "id": str(r.id),
            "team_name": r.team_name,
            "specialization": r.specialization,
            "status": r.status,
            "shift_hours": f"{r.shift_start_hour:02d}:00 - {r.shift_end_hour:02d}:00",
            "burnout_index": r.burnout_index,
            "cumulative_shifts_week": r.cumulative_shifts_week,
            "location": {"latitude": r.lat, "longitude": r.lon},
        }
        for r in rows
    ]


@router.post("/optimize")
async def optimize_dispatch_schedule(
    current_hour: int = Query(default=14, ge=0, le=23),
    current_user: UserOrm = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Executes Z3 MaxSMT formal Pareto optimization to compute verified dispatch assignments."""
    async with UnitOfWork(session) as uow:
        # Fetch active untriaged or pending incidents
        inc_stmt = select(
            IncidentOrm.id,
            IncidentOrm.title,
            IncidentOrm.category,
            IncidentOrm.urgency,
            IncidentOrm.modality,
            IncidentOrm.source_protocol,
            IncidentOrm.created_at,
            IncidentOrm.updated_at,
            IncidentOrm.triage_state,
            func.ST_X(IncidentOrm.location).label("lon"),
            func.ST_Y(IncidentOrm.location).label("lat"),
        ).where(IncidentOrm.triage_state.in_(["TRIAGED", "QUEUED"])).limit(20)

        inc_res = await uow.session.execute(inc_stmt)
        inc_rows = inc_res.fetchall()

        # Fetch idle teams on shift
        team_stmt = select(
            FieldTeamOrm.id,
            FieldTeamOrm.team_name,
            FieldTeamOrm.specialization,
            FieldTeamOrm.status,
            FieldTeamOrm.shift_start_hour,
            FieldTeamOrm.shift_end_hour,
            FieldTeamOrm.burnout_index,
            FieldTeamOrm.cumulative_shifts_week,
            FieldTeamOrm.created_at,
            FieldTeamOrm.updated_at,
            func.ST_X(FieldTeamOrm.current_location).label("lon"),
            func.ST_Y(FieldTeamOrm.current_location).label("lat"),
        ).where(FieldTeamOrm.status == "IDLE")

        team_res = await uow.session.execute(team_stmt)
        team_rows = team_res.fetchall()

        if not inc_rows or not team_rows:
            return {
                "status": "NO_DISPATCH_NEEDED",
                "message": "No pending incidents or no idle teams available.",
                "assignments": [],
            }

        # Convert to pure domain entities
        inc_entities = [
            IncidentEntity(
                id=r.id,
                title=r.title,
                description_scrubbed=r.title,
                urgency=r.urgency,
                category=r.category,
                modality=r.modality,
                source_protocol=r.source_protocol,
                location=GeoCoordinates(latitude=r.lat, longitude=r.lon),
                triage_state=r.triage_state,
                created_at=r.created_at,
                updated_at=r.updated_at,
            )
            for r in inc_rows
        ]

        team_entities = [
            FieldTeamEntity(
                id=r.id,
                team_name=r.team_name,
                specialization=r.specialization,
                current_location=GeoCoordinates(latitude=r.lat, longitude=r.lon),
                status=r.status,
                shift_start_hour=r.shift_start_hour,
                shift_end_hour=r.shift_end_hour,
                burnout_index=r.burnout_index,
                cumulative_shifts_week=r.cumulative_shifts_week,
                created_at=r.created_at,
                updated_at=r.updated_at,
            )
            for r in team_rows
        ]

        # Run Z3 MaxSMT
        assignments = _dispatcher.optimize_dispatch(inc_entities, team_entities, current_hour)

        out_assignments = []
        for inc_e, team_e, eta, proof in assignments:
            disp_id = uuid.uuid4()
            disp_orm = DispatchScheduleOrm(
                id=disp_id,
                incident_id=inc_e.id,
                team_id=team_e.id,
                estimated_arrival_minutes=eta,
                priority_weight=1.0,
                smt_proof={
                    "is_sat": proof.is_sat,
                    "objective_val": proof.objective_value,
                    "slack": list(proof.slack_variables),
                },
                is_active=True,
            )
            await uow.dispatches.create(disp_orm)

            # Update team and incident state
            team_db = await uow.teams.get_by_id(team_e.id)
            if team_db:
                team_db.status = "DISPATCHED"
                team_db.burnout_index = min(1.0, team_db.burnout_index + 0.05)

            inc_db = await uow.incidents.get_by_id(inc_e.id)
            if inc_db:
                inc_db.triage_state = "DISPATCHED"

            # Domain event
            ev = SmtDispatchOptimizedEvent(
                aggregate_type="DispatchSchedule",
                aggregate_id=disp_id,
                event_type="SmtDispatchOptimized",
                payload={
                    "dispatch_id": str(disp_id),
                    "incident_id": str(inc_e.id),
                    "team_id": str(team_e.id),
                    "team_name": team_e.team_name,
                    "eta_minutes": eta,
                },
            ).sign()

            await uow.outbox.enqueue(
                aggregate_type="DispatchSchedule",
                aggregate_id=disp_id,
                event_type="SmtDispatchOptimized",
                payload=ev.payload,
                routing_key="dispatch.event.optimized",
            )

            out_assignments.append({
                "dispatch_id": str(disp_id),
                "incident_id": str(inc_e.id),
                "incident_title": inc_e.title,
                "team_id": str(team_e.id),
                "team_name": team_e.team_name,
                "estimated_arrival_minutes": round(eta, 1),
                "formal_smt_verified": proof.is_sat,
            })

        return {
            "status": "OPTIMIZED_SAT",
            "solved_assignments_count": len(out_assignments),
            "assignments": out_assignments,
        }
