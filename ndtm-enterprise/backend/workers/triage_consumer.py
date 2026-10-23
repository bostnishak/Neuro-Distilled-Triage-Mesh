"""Asynchronous incident triage worker consuming q.triage.process."""
from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID

from aio_pika.abc import AbstractIncomingMessage
from sqlalchemy import update

from backend.core.logging import setup_enterprise_logging
from backend.db.models import Incident
from backend.db.session import async_session_factory
from backend.schemas.triage import TicketStatus
from backend.services.websocket_manager import ws_manager
from backend.workers.rabbitmq_client import RabbitMQClient

setup_enterprise_logging("INFO")
logger = logging.getLogger("workers.triage_consumer")


async def handle_triage_incident(payload: dict[str, Any], message: AbstractIncomingMessage) -> None:
    incident_id_str = payload.get("incident_id")
    if not incident_id_str:
        logger.warning("Received invalid triage event payload: %s", payload)
        return

    incident_id = UUID(incident_id_str)
    category = payload.get("category", "GENERAL")
    logger.info("Processing async triage event for incident %s (%s)...", incident_id, category)

    # 1. Update database status to TRIAGED
    async with async_session_factory() as session:
        async with session.begin():
            stmt = (
                update(Incident)
                .where(Incident.id == incident_id)
                .values(status=TicketStatus.TRIAGED.value)
            )
            await session.execute(stmt)

    logger.info("Incident %s successfully transitioned to TRIAGED.", incident_id)

    # 2. Broadcast real-time event to WebSocket cockpit
    await ws_manager.broadcast_event(
        "incident_triaged",
        {
            "incident_id": str(incident_id),
            "category": category,
            "urgency_score": payload.get("urgency_score", 5),
            "status": TicketStatus.TRIAGED.value,
        },
    )


async def main() -> None:
    client = RabbitMQClient()
    await client.connect()
    logger.info("Incident Triage Consumer Worker started.")
    try:
        await client.consume_queue("q.triage.process", handle_triage_incident)
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
