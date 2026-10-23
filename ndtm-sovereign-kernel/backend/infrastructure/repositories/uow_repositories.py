import datetime
import uuid
from typing import Any, Dict, List, Optional
from sqlalchemy import select, update, func, text, desc
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.database.orm_models import (
    IncidentOrm,
    IncidentClusterOrm,
    FieldTeamOrm,
    DispatchScheduleOrm,
    TransactionalOutboxOrm,
    KernelDomainEventOrm,
    MerkleAuditBlockOrm,
    HitlApprovalRequestOrm,
    UserOrm,
)
from domain.entities import (
    IncidentEntity,
    FieldTeamEntity,
    IncidentClusterEntity,
    DispatchScheduleEntity,
    UserEntity,
)
from domain.value_objects import GeoCoordinates, EmbeddingVector, MelSpectrogram
from core.exceptions import NotFoundError, ConflictError


class IncidentRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, incident_id: uuid.UUID) -> Optional[IncidentOrm]:
        stmt = select(IncidentOrm).where(IncidentOrm.id == incident_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, incident: IncidentOrm) -> IncidentOrm:
        self._session.add(incident)
        await self._session.flush()
        return incident

    async def list_active(self, limit: int = 50, offset: int = 0) -> List[IncidentOrm]:
        stmt = (
            select(IncidentOrm)
            .where(IncidentOrm.triage_state != "RESOLVED")
            .order_by(desc(IncidentOrm.created_at))
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def find_spatial_neighbors(
        self,
        longitude: float,
        latitude: float,
        radius_meters: float = 1000.0,
        time_window_hours: int = 6,
    ) -> List[IncidentOrm]:
        """Finds incidents within radius and time window using PostGIS ST_DWithin."""
        point_wkt = f"SRID=4326;POINT({longitude:.7f} {latitude:.7f})"
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=time_window_hours)

        stmt = (
            select(IncidentOrm)
            .where(
                func.ST_DWithin(
                    IncidentOrm.location,
                    func.ST_GeomFromEWKT(point_wkt),
                    radius_meters,
                    True,  # use spheroid
                )
            )
            .where(IncidentOrm.created_at >= cutoff)
            .order_by(desc(IncidentOrm.created_at))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def find_semantic_neighbors(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        threshold: float = 0.80,
    ) -> List[IncidentOrm]:
        """Finds top-k semantically similar incidents via pgvector cosine distance `<=>`."""
        stmt = (
            select(IncidentOrm)
            .where(IncidentOrm.embedding.is_not(None))
            .order_by(IncidentOrm.embedding.cosine_distance(query_embedding))
            .limit(top_k)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class ClusterRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, cluster_id: uuid.UUID) -> Optional[IncidentClusterOrm]:
        stmt = select(IncidentClusterOrm).where(IncidentClusterOrm.id == cluster_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, cluster: IncidentClusterOrm) -> IncidentClusterOrm:
        self._session.add(cluster)
        await self._session.flush()
        return cluster

    async def find_matching_cluster(
        self,
        longitude: float,
        latitude: float,
        buffer_meters: float = 500.0,
    ) -> Optional[IncidentClusterOrm]:
        point_wkt = f"SRID=4326;POINT({longitude:.7f} {latitude:.7f})"
        stmt = (
            select(IncidentClusterOrm)
            .where(IncidentClusterOrm.status == "ACTIVE")
            .where(
                func.ST_DWithin(
                    IncidentClusterOrm.centroid,
                    func.ST_GeomFromEWKT(point_wkt),
                    IncidentClusterOrm.radius_meters + buffer_meters,
                    True,
                )
            )
            .order_by(desc(IncidentClusterOrm.updated_at))
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


class FieldTeamRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, team_id: uuid.UUID) -> Optional[FieldTeamOrm]:
        stmt = select(FieldTeamOrm).where(FieldTeamOrm.id == team_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_available(self, current_hour: int) -> List[FieldTeamOrm]:
        stmt = (
            select(FieldTeamOrm)
            .where(FieldTeamOrm.status == "IDLE")
            .where(FieldTeamOrm.shift_start_hour <= current_hour)
            .where(FieldTeamOrm.shift_end_hour > current_hour)
            .where(FieldTeamOrm.burnout_index < 0.85)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class DispatchRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, dispatch: DispatchScheduleOrm) -> DispatchScheduleOrm:
        self._session.add(dispatch)
        await self._session.flush()
        return dispatch

    async def get_by_incident_id(self, incident_id: uuid.UUID) -> Optional[DispatchScheduleOrm]:
        stmt = select(DispatchScheduleOrm).where(
            DispatchScheduleOrm.incident_id == incident_id,
            DispatchScheduleOrm.is_active == True,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


class OutboxRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def enqueue(
        self,
        aggregate_type: str,
        aggregate_id: uuid.UUID,
        event_type: str,
        payload: Dict[str, Any],
        routing_key: str,
    ) -> TransactionalOutboxOrm:
        outbox_entry = TransactionalOutboxOrm(
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_type=event_type,
            payload=payload,
            routing_key=routing_key,
        )
        self._session.add(outbox_entry)
        await self._session.flush()
        return outbox_entry

    async def fetch_unpublished(self, batch_size: int = 50) -> List[TransactionalOutboxOrm]:
        """Fetches pending outbox records using SELECT ... FOR UPDATE SKIP LOCKED for concurrent safety."""
        stmt = (
            select(TransactionalOutboxOrm)
            .where(TransactionalOutboxOrm.published_at.is_(None))
            .where(TransactionalOutboxOrm.retry_count < 5)
            .order_by(TransactionalOutboxOrm.id.asc())
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def mark_published(self, record_ids: List[int]) -> None:
        if not record_ids:
            return
        now = datetime.datetime.now(datetime.timezone.utc)
        stmt = (
            update(TransactionalOutboxOrm)
            .where(TransactionalOutboxOrm.id.in_(record_ids))
            .values(published_at=now)
        )
        await self._session.execute(stmt)


class EventStoreRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def append(self, event_orm: KernelDomainEventOrm) -> KernelDomainEventOrm:
        self._session.add(event_orm)
        await self._session.flush()
        return event_orm

    async def get_unsealed_events(self, limit: int = 100) -> List[KernelDomainEventOrm]:
        stmt = (
            select(KernelDomainEventOrm)
            .order_by(KernelDomainEventOrm.occurred_at.asc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class MerkleChainRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_latest_block(self) -> Optional[MerkleAuditBlockOrm]:
        stmt = (
            select(MerkleAuditBlockOrm)
            .order_by(desc(MerkleAuditBlockOrm.height))
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def append_block(self, block: MerkleAuditBlockOrm) -> MerkleAuditBlockOrm:
        self._session.add(block)
        await self._session.flush()
        return block


class UnitOfWork:
    """Transactional Unit of Work managing database sessions and repository lifecycles."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.incidents = IncidentRepository(session)
        self.clusters = ClusterRepository(session)
        self.teams = FieldTeamRepository(session)
        self.dispatches = DispatchRepository(session)
        self.outbox = OutboxRepository(session)
        self.events = EventStoreRepository(session)
        self.merkle = MerkleChainRepository(session)

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()

    async def __aenter__(self) -> "UnitOfWork":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if exc_type is not None:
            await self.rollback()
        else:
            await self.commit()
