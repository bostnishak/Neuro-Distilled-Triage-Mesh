"""RabbitMQ (AMQP 0-9-1) client built on aio-pika.

Topology
--------
    [triage] --triage.new--> (triage_queue) --dead-letter--> [triage.dlx] --triage.dead--> (triage_dlq)
                                   ^
    (triage_retry, TTL=N ms) ------+   (expired messages dead-letter back to [triage])

* Publisher confirms + persistent messages => at-least-once delivery.
* Workers retry transient failures through `triage_retry` (delayed redelivery)
  and reject poison messages to the DLQ after `triage_max_retries`.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import aio_pika
from aio_pika import DeliveryMode, ExchangeType, Message
from aio_pika.abc import AbstractChannel, AbstractExchange, AbstractQueue, AbstractRobustConnection

from core.config import Settings

logger = logging.getLogger(__name__)


class BrokerNotConnectedError(RuntimeError):
    """Raised when publishing before `connect()` succeeded."""


class RabbitBroker:
    """Thin, resilient wrapper around a robust aio-pika connection."""

    def __init__(self, settings: Settings) -> None:
        self._s = settings
        self._connection: AbstractRobustConnection | None = None
        self._channel: AbstractChannel | None = None
        self._exchange: AbstractExchange | None = None
        self._queues: dict[str, AbstractQueue] = {}

    # ------------------------------------------------------------------ lifecycle
    async def connect(self, attempts: int = 30) -> None:
        """Connect (with backoff), open a confirm channel and declare topology."""
        for attempt in range(1, attempts + 1):
            try:
                self._connection = await aio_pika.connect_robust(
                    self._s.rabbitmq_url,
                    client_properties={"connection_name": self._s.app_name},
                )
                break
            except Exception as exc:  # noqa: BLE001 - aiormq raises a variety of errors
                if attempt == attempts:
                    logger.error("Giving up connecting to RabbitMQ", exc_info=True)
                    raise
                delay = min(2 ** (attempt - 1) * 0.5, 10.0)
                logger.warning("RabbitMQ not ready (%s); retry %d/%d in %.1fs", exc, attempt, attempts, delay)
                await asyncio.sleep(delay)

        assert self._connection is not None
        self._channel = await self._connection.channel(publisher_confirms=True)
        await self._channel.set_qos(prefetch_count=self._s.worker_prefetch)
        await self.declare_topology()
        logger.info("RabbitMQ connected and topology declared")

    async def declare_topology(self) -> None:
        """Idempotently declare exchanges, queues and bindings."""
        ch = self._require_channel()
        s = self._s
        self._exchange = await ch.declare_exchange(s.triage_exchange, ExchangeType.DIRECT, durable=True)
        dlx = await ch.declare_exchange(s.triage_dlx, ExchangeType.DIRECT, durable=True)

        main_q = await ch.declare_queue(
            s.triage_queue,
            durable=True,
            arguments={
                "x-dead-letter-exchange": s.triage_dlx,
                "x-dead-letter-routing-key": s.triage_dead_routing_key,
            },
        )
        await main_q.bind(self._exchange, routing_key=s.triage_routing_key)

        retry_q = await ch.declare_queue(
            s.triage_retry_queue,
            durable=True,
            arguments={
                "x-message-ttl": s.triage_retry_delay_ms,
                "x-dead-letter-exchange": s.triage_exchange,
                "x-dead-letter-routing-key": s.triage_routing_key,
            },
        )

        dlq = await ch.declare_queue(s.triage_dlq, durable=True)
        await dlq.bind(dlx, routing_key=s.triage_dead_routing_key)

        self._queues = {s.triage_queue: main_q, s.triage_retry_queue: retry_q, s.triage_dlq: dlq}

    async def close(self) -> None:
        if self._connection is not None and not self._connection.is_closed:
            await self._connection.close()
            logger.info("RabbitMQ connection closed")

    # ------------------------------------------------------------------ publishing
    async def publish(
        self,
        payload: dict[str, Any],
        *,
        routing_key: str | None = None,
        message_id: str | None = None,
        headers: dict[str, Any] | None = None,
        timeout: float = 10.0,
    ) -> None:
        """Publish a persistent JSON message to the triage exchange (awaits broker confirm)."""
        if self._exchange is None:
            raise BrokerNotConnectedError("RabbitMQ exchange not initialised")
        message = Message(
            body=json.dumps(payload, default=str).encode("utf-8"),
            content_type="application/json",
            delivery_mode=DeliveryMode.PERSISTENT,
            message_id=message_id or uuid4().hex,
            timestamp=datetime.now(timezone.utc),
            headers=headers or {},
        )
        await self._exchange.publish(message, routing_key=routing_key or self._s.triage_routing_key,
                                     timeout=timeout)

    async def publish_to_queue(self, queue_name: str, body: bytes, *, headers: dict[str, Any],
                               message_id: str | None = None) -> None:
        """Publish raw bytes directly to a queue via the default exchange (used for retries)."""
        ch = self._require_channel()
        await ch.default_exchange.publish(
            Message(body=body, content_type="application/json", delivery_mode=DeliveryMode.PERSISTENT,
                    headers=headers, message_id=message_id),
            routing_key=queue_name,
            timeout=10.0,
        )

    # ------------------------------------------------------------------ helpers
    def get_queue(self, name: str) -> AbstractQueue:
        try:
            return self._queues[name]
        except KeyError as exc:
            raise BrokerNotConnectedError(f"Queue {name!r} not declared") from exc

    def is_healthy(self) -> bool:
        return self._connection is not None and not self._connection.is_closed

    def _require_channel(self) -> AbstractChannel:
        if self._channel is None:
            raise BrokerNotConnectedError("RabbitMQ channel not initialised")
        return self._channel
