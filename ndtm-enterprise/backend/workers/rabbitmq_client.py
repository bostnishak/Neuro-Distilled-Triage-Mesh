"""RabbitMQ connection manager and AMQP consumer helper with Dead Letter handling."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable

import aio_pika
from aio_pika.abc import AbstractIncomingMessage

from backend.core.config import get_settings

logger = logging.getLogger("workers.rabbitmq_client")
settings = get_settings()


class RabbitMQClient:
    def __init__(self) -> None:
        self.connection: aio_pika.RobustConnection | None = None
        self.channel: aio_pika.RobustChannel | None = None

    async def connect(self) -> None:
        """Establishes robust connection with auto-reconnection and declares topology."""
        logger.info("Connecting to RabbitMQ at %s...", settings.RABBITMQ_HOST)
        self.connection = await aio_pika.connect_robust(
            settings.RABBITMQ_URL,
            timeout=10.0,
        )
        self.channel = await self.connection.channel()
        await self.channel.set_qos(prefetch_count=20)
        logger.info("RabbitMQ connection established.")

    async def consume_queue(
        self,
        queue_name: str,
        message_handler: Callable[[dict[str, Any], AbstractIncomingMessage], Any],
    ) -> None:
        """Subscribes a consumer callback to a queue with ACK/NACK dead-letter guarantees."""
        if not self.channel:
            await self.connect()

        assert self.channel is not None
        queue = await self.channel.get_queue(queue_name)
        logger.info("Starting consumer subscription on queue '%s'...", queue_name)

        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                async with message.process(requeue=False, ignore_processed=True):
                    try:
                        payload = json.loads(message.body.decode("utf-8"))
                        await message_handler(payload, message)
                        await message.ack()
                    except Exception as err:
                        logger.error(
                            "Message processing failed in queue %s. Routing to DLQ: %s",
                            queue_name,
                            err,
                        )
                        # Reject message so RabbitMQ moves it to the dead letter exchange (ndtm.dlx.direct)
                        await message.reject(requeue=False)

    async def close(self) -> None:
        if self.channel and not self.channel.is_closed:
            await self.channel.close()
        if self.connection and not self.connection.is_closed:
            await self.connection.close()
        logger.info("RabbitMQ client closed.")
