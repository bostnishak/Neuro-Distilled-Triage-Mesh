"""Transactional Outbox Relay Worker.

Polls outbox_events every 250ms using SELECT ... FOR UPDATE SKIP LOCKED,
publishes messages to RabbitMQ topic exchange with Publisher Confirms enabled,
and atomically updates published = TRUE.
"""
from __future__ import annotations

import asyncio
import json
import logging
import signal
import sys
from typing import Any

import aio_pika
from sqlalchemy import select, update

from backend.core.config import get_settings
from backend.core.logging import setup_enterprise_logging
from backend.db.models import OutboxEvent
from backend.db.session import async_session_factory

setup_enterprise_logging("INFO")
logger = logging.getLogger("outbox_relay")
settings = get_settings()

_running = True


def handle_shutdown_signal(sig: int, frame: Any) -> None:
    global _running
    logger.info("Received termination signal (%s). Shutting down Outbox Relay...", sig)
    _running = False


signal.signal(signal.SIGINT, handle_shutdown_signal)
signal.signal(signal.SIGTERM, handle_shutdown_signal)


class TransactionalOutboxRelay:
    def __init__(self) -> None:
        self.rmq_connection: aio_pika.RobustConnection | None = None
        self.rmq_channel: aio_pika.RobustChannel | None = None
        self.topic_exchange: aio_pika.RobustExchange | None = None

    async def connect_rabbitmq(self) -> None:
        """Connects to RabbitMQ with robust auto-reconnection and enables publisher confirms."""
        logger.info("Connecting Outbox Relay to RabbitMQ: %s", settings.RABBITMQ_HOST)
        self.rmq_connection = await aio_pika.connect_robust(
            settings.RABBITMQ_URL,
            timeout=10.0,
        )
        self.rmq_channel = await self.rmq_connection.channel(publisher_confirms=True)
        await self.rmq_channel.set_qos(prefetch_count=50)

        self.topic_exchange = await self.rmq_channel.declare_exchange(
            "ndtm.events.topic",
            aio_pika.ExchangeType.TOPIC,
            durable=True,
        )
        logger.info("RabbitMQ Outbox Relay channel ready with Publisher Confirms.")

    async def run(self) -> None:
        """Main polling loop with 250ms interval and SKIP LOCKED concurrency protection."""
        await self.connect_rabbitmq()

        poll_interval_sec = settings.OUTBOX_POLL_INTERVAL_MS / 1000.0
        logger.info("Outbox Relay running. Polling every %.3fs...", poll_interval_sec)

        while _running:
            try:
                processed_count = await self.poll_and_relay_batch()
                if processed_count == 0:
                    await asyncio.sleep(poll_interval_sec)
            except Exception as exc:
                logger.error("Outbox Relay encountered error in polling cycle: %s", exc)
                await asyncio.sleep(1.0)

        await self.shutdown()

    async def poll_and_relay_batch(self, batch_size: int = 50) -> int:
        """Processes up to 50 unpublished events in a single transactional lock."""
        async with async_session_factory() as session:
            async with session.begin():
                # 1. Fetch unpublished events locking only targeted rows
                stmt = (
                    select(OutboxEvent)
                    .where(OutboxEvent.published == False)  # noqa: E712
                    .order_by(OutboxEvent.created_at.asc())
                    .limit(batch_size)
                    .with_for_update(skip_locked=True)
                )
                res = await session.execute(stmt)
                events = res.scalars().all()

                if not events:
                    return 0

                published_ids: list[Any] = []
                for event in events:
                    try:
                        # 2. Serialize and publish with Publisher Confirms
                        message_body = json.dumps(event.payload, ensure_ascii=False).encode("utf-8")
                        message = aio_pika.Message(
                            body=message_body,
                            content_type="application/json",
                            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                            headers={"aggregate_type": event.aggregate_type, "aggregate_id": str(event.aggregate_id)},
                            message_id=str(event.id),
                        )

                        # Publish to Topic Exchange
                        confirmation = await self.topic_exchange.publish(  # type: ignore
                            message,
                            routing_key=event.routing_key,
                        )
                        # Publisher Confirms guarantee the broker persisted message to disk/queue
                        published_ids.append(event.id)
                    except Exception as pub_err:
                        logger.error("Failed to publish event %s: %s", event.id, pub_err)
                        event.retry_count += 1

                # 3. Mark successfully confirmed events as published
                if published_ids:
                    from datetime import datetime, timezone
                    await session.execute(
                        update(OutboxEvent)
                        .where(OutboxEvent.id.in_(published_ids))
                        .values(published=True, published_at=datetime.now(timezone.utc))
                    )
                    logger.info("Successfully published and confirmed %d outbox events.", len(published_ids))

                return len(published_ids)

    async def shutdown(self) -> None:
        """Gracefully releases RabbitMQ connection."""
        logger.info("Closing Outbox Relay RabbitMQ resources...")
        if self.rmq_channel and not self.rmq_channel.is_closed:
            await self.rmq_channel.close()
        if self.rmq_connection and not self.rmq_connection.is_closed:
            await self.rmq_connection.close()
        logger.info("Outbox Relay shutdown complete.")


if __name__ == "__main__":
    relay = TransactionalOutboxRelay()
    asyncio.run(relay.run())
