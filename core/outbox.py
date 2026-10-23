"""Transactional outbox.

Writing the ticket and its "ticket.created" event in the SAME database
transaction removes the dual-write problem (DB commit succeeds but the
RabbitMQ publish fails, or vice versa). A relay loop publishes pending rows
and marks them as sent; consumers are idempotent so at-least-once is safe.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any
from uuid import UUID

import asyncpg

from core.broker import RabbitBroker
from core.config import Settings

logger = logging.getLogger(__name__)


async def enqueue_outbox(conn: asyncpg.Connection, *, aggregate_id: UUID, routing_key: str,
                         payload: dict[str, Any]) -> int:
    """Insert an outbox event inside the caller's transaction."""
    return await conn.fetchval(
        "INSERT INTO outbox_events (aggregate_id, routing_key, payload) VALUES ($1, $2, $3) RETURNING id",
        aggregate_id, routing_key, payload,
    )


class OutboxRelay:
    """Background publisher draining `outbox_events` into RabbitMQ."""

    def __init__(self, pool: asyncpg.Pool, broker: RabbitBroker, settings: Settings,
                 batch_size: int = 100) -> None:
        self._pool = pool
        self._broker = broker
        self._interval = settings.outbox_poll_interval_seconds
        self._batch_size = batch_size
        self._wake = asyncio.Event()
        self._stopping = asyncio.Event()

    def notify(self) -> None:
        """Wake the relay immediately (called right after a commit)."""
        self._wake.set()

    def stop(self) -> None:
        self._stopping.set()
        self._wake.set()

    async def run(self) -> None:
        logger.info("Outbox relay started")
        while not self._stopping.is_set():
            self._wake.clear()  # clear BEFORE draining so notifications during a drain aren't lost
            try:
                published = await self.publish_pending()
                if published:
                    logger.info("Outbox relay published %d event(s)", published)
                    continue  # there may be more; loop immediately
            except Exception:  # noqa: BLE001 - relay must never die
                logger.exception("Outbox relay iteration failed")
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self._wake.wait(), timeout=self._interval)
        logger.info("Outbox relay stopped")

    async def publish_pending(self) -> int:
        """Publish one batch. Rows are locked with SKIP LOCKED so multiple API replicas can relay safely."""
        published = 0
        async with self._pool.acquire() as conn, conn.transaction():
            rows = await conn.fetch(
                """
                SELECT id, routing_key, payload
                FROM outbox_events
                WHERE published_at IS NULL
                ORDER BY id
                LIMIT $1
                FOR UPDATE SKIP LOCKED
                """,
                self._batch_size,
            )
            for row in rows:
                payload = dict(row["payload"])
                try:
                    await self._broker.publish(
                        payload,
                        routing_key=row["routing_key"],
                        message_id=f"outbox-{row['id']}",
                        headers={"x-request-id": payload.get("request_id", "-")},
                    )
                except Exception as exc:  # noqa: BLE001
                    await conn.execute(
                        "UPDATE outbox_events SET attempts = attempts + 1, last_error = $2 WHERE id = $1",
                        row["id"], str(exc)[:1000],
                    )
                    logger.warning("Outbox publish failed for event %s: %s", row["id"], exc)
                    break  # broker is probably down; retry the remainder on the next tick
                await conn.execute(
                    "UPDATE outbox_events SET attempts = attempts + 1, published_at = now() WHERE id = $1",
                    row["id"],
                )
                published += 1
        return published
