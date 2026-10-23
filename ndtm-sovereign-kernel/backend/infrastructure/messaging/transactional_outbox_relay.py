import asyncio
import json
from typing import Optional
import aio_pika
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.logging_otel import logger
from infrastructure.database.connection import AsyncSessionLocal
from infrastructure.repositories.uow_repositories import UnitOfWork


class TransactionalOutboxRelay:
    """Asynchronous worker that polls transactional_outbox and publishes events to RabbitMQ."""

    def __init__(self, poll_interval_seconds: float = 0.5, batch_size: int = 50):
        self.poll_interval_seconds = poll_interval_seconds
        self.batch_size = batch_size
        self._is_running = False
        self._connection: Optional[aio_pika.abc.AbstractRobustConnection] = None
        self._channel: Optional[aio_pika.abc.AbstractRobustChannel] = None
        self._exchange: Optional[aio_pika.abc.AbstractRobustExchange] = None

    async def initialize_amqp(self) -> None:
        """Connects to RabbitMQ and declares the topic exchange."""
        self._connection = await aio_pika.connect_robust(settings.rabbitmq_url)
        self._channel = await self._connection.channel()
        self._exchange = await self._channel.declare_exchange(
            "ndtm.events.topic",
            aio_pika.ExchangeType.TOPIC,
            durable=True,
        )
        logger.info("amqp_outbox_relay_initialized", exchange="ndtm.events.topic")

    async def run(self) -> None:
        """Main daemon loop."""
        self._is_running = True
        logger.info("outbox_relay_loop_started")

        while self._is_running:
            try:
                if self._exchange is None:
                    await self.initialize_amqp()

                published_ids = []
                async with AsyncSessionLocal() as session:
                    async with UnitOfWork(session) as uow:
                        pending_records = await uow.outbox.fetch_unpublished(batch_size=self.batch_size)

                        if pending_records:
                            assert self._exchange is not None
                            for record in pending_records:
                                try:
                                    message_body = json.dumps(record.payload).encode("utf-8")
                                    message = aio_pika.Message(
                                        body=message_body,
                                        content_type="application/json",
                                        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                                        headers={
                                            "aggregate_type": record.aggregate_type,
                                            "aggregate_id": str(record.aggregate_id),
                                            "event_type": record.event_type,
                                        },
                                    )
                                    await self._exchange.publish(
                                        message,
                                        routing_key=record.routing_key,
                                    )
                                    published_ids.append(record.id)
                                except Exception as pub_err:
                                    record.retry_count += 1
                                    record.last_error = str(pub_err)
                                    logger.error(
                                        "outbox_publish_failed",
                                        record_id=record.id,
                                        error=str(pub_err),
                                    )

                            if published_ids:
                                await uow.outbox.mark_published(published_ids)

                if not published_ids:
                    await asyncio.sleep(self.poll_interval_seconds)

            except asyncio.CancelledError:
                self._is_running = False
                break
            except Exception as e:
                logger.error("outbox_relay_loop_error", error=str(e))
                await asyncio.sleep(2.0)

    async def stop(self) -> None:
        """Gracefully halts relay."""
        self._is_running = False
        if self._connection and not self._connection.is_closed:
            await self._connection.close()
        logger.info("outbox_relay_stopped")
