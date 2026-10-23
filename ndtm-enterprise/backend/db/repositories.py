"""Transactional repository layer for database mutations and atomic outbox writes."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Sequence
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import (
    DispatchSchedule,
    FieldTeam,
    IdempotencyRecord,
    Incident,
    OutboxEvent,
    RouterTelemetryLog,
    ShadowDriftSample,
    User,
)
from backend.schemas.auth import UserRole
from backend.schemas.triage import TicketStatus

logger = logging.getLogger("db.repositories")


class UserRepository:
    @staticmethod
    async def get_by_email(session: AsyncSession, email: str) -> User | None:
        query = select(User).where(User.email == email)
        res = await session.execute(query)
        return res.scalar_one_or_none()

    @staticmethod
    async def get_by_id(session: AsyncSession, user_id: UUID) -> User | None:
        return await session.get(User, user_id)

    @staticmethod
    async def create(session: AsyncSession, email: str, password_hash: str, role: UserRole) -> User:
        user = User(email=email, password_hash=password_hash, role=role.value)
        session.add(user)
        await session.flush()
        return user


class IncidentRepository:
    @staticmethod
    async def create_with_outbox(
        session: AsyncSession,
        incident: Incident,
        outbox_payload: dict[str, Any],
        routing_key: str = "triage.incident.created",
    ) -> Incident:
        """Atomically inserts incident record and corresponding OutboxEvent within the same transaction."""
        session.add(incident)
        await session.flush()

        outbox_event = OutboxEvent(
            aggregate_type="incident",
            aggregate_id=incident.id,
            routing_key=routing_key,
            payload=outbox_payload,
            published=False,
        )
        session.add(outbox_event)
        await session.flush()
        return incident

    @staticmethod
    async def increment_duplicate_count(session: AsyncSession, parent_id: UUID) -> int:
        """Atomically increments duplicate counter on master incident."""
        stmt = (
            update(Incident)
            .where(Incident.id == parent_id)
            .values(duplicate_count=Incident.duplicate_count + 1)
            .returning(Incident.duplicate_count)
        )
        res = await session.execute(stmt)
        new_count = res.scalar_one()
        return new_count

    @staticmethod
    async def get_by_id(session: AsyncSession, incident_id: UUID) -> Incident | None:
        return await session.get(Incident, incident_id)

    @staticmethod
    async def list_recent(session: AsyncSession, limit: int = 50) -> Sequence[Incident]:
        stmt = select(Incident).order_by(Incident.created_at.desc()).limit(limit)
        res = await session.execute(stmt)
        return res.scalars().all()


class OutboxRepository:
    @staticmethod
    async def fetch_unpublished_for_update(
        session: AsyncSession, limit: int = 50
    ) -> Sequence[OutboxEvent]:
        """Polls unpublished events using SELECT ... FOR UPDATE SKIP LOCKED to prevent worker collisions."""
        stmt = (
            select(OutboxEvent)
            .where(OutboxEvent.published == False)  # noqa: E712
            .order_by(OutboxEvent.created_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        res = await session.execute(stmt)
        return res.scalars().all()

    @staticmethod
    async def mark_published(session: AsyncSession, event_ids: list[UUID]) -> None:
        if not event_ids:
            return
        stmt = (
            update(OutboxEvent)
            .where(OutboxEvent.id.in_(event_ids))
            .values(published=True, published_at=datetime.now(timezone.utc))
        )
        await session.execute(stmt)


class FieldTeamRepository:
    @staticmethod
    async def get_available_teams(session: AsyncSession) -> Sequence[FieldTeam]:
        stmt = select(FieldTeam).where(FieldTeam.is_available == True)  # noqa: E712
        res = await session.execute(stmt)
        return res.scalars().all()


class DispatchScheduleRepository:
    @staticmethod
    async def save_schedule(
        session: AsyncSession,
        incident_id: UUID,
        team_id: UUID,
        travel_min: int,
        work_min: int,
        z3_proof_smt2: str,
        iterations: int = 0,
    ) -> DispatchSchedule:
        schedule = DispatchSchedule(
            incident_id=incident_id,
            team_id=team_id,
            estimated_travel_minutes=travel_min,
            estimated_work_minutes=work_min,
            z3_proof_smt2=z3_proof_smt2,
            correction_iterations=iterations,
        )
        session.add(schedule)
        await session.flush()
        return schedule


class TelemetryRepository:
    @staticmethod
    async def log_router_execution(
        session: AsyncSession,
        request_id: str,
        execution_target: str,
        student_entropy: float | None,
        ood_similarity: float | None,
        latency_ms: float,
        cost_saved_usd: float = 0.0,
    ) -> None:
        log_entry = RouterTelemetryLog(
            request_id=request_id,
            execution_target=execution_target,
            student_entropy=student_entropy,
            ood_similarity=ood_similarity,
            latency_ms=latency_ms,
            cost_saved_usd=cost_saved_usd,
        )
        session.add(log_entry)
        await session.flush()

    @staticmethod
    async def save_shadow_sample(
        session: AsyncSession,
        request_id: str,
        input_text: str,
        student_output: dict[str, Any],
        teacher_output: dict[str, Any],
        kl_divergence: float,
    ) -> ShadowDriftSample:
        sample = ShadowDriftSample(
            request_id=request_id,
            input_text=input_text,
            student_output=student_output,
            teacher_output=teacher_output,
            kl_divergence=kl_divergence,
            used_for_retraining=False,
        )
        session.add(sample)
        await session.flush()
        return sample

    @staticmethod
    async def get_unretrained_drift_samples(
        session: AsyncSession, limit: int = 1000
    ) -> Sequence[ShadowDriftSample]:
        stmt = (
            select(ShadowDriftSample)
            .where(ShadowDriftSample.used_for_retraining == False)  # noqa: E712
            .order_by(ShadowDriftSample.kl_divergence.desc())
            .limit(limit)
        )
        res = await session.execute(stmt)
        return res.scalars().all()
