"""Asynchronous background worker consuming `triage_queue` from RabbitMQ.

Responsibilities:
1. Message ingestion with aio-pika.
2. Context propagation (Request ID).
3. Retrieval of ticket from PostgreSQL.
4. Execution of DistillMesh semantic routing inference (ONNX student or Teacher LLM).
5. Atomic update of ticket record (intent, urgency, priority, entities, triage_route, status).
6. Routing telemetry logging to `inference_logs`.
7. Dead-lettering and retry logic with max retry limits.
"""
from __future__ import annotations

import asyncio
import json
import logging
import signal
import sys
from typing import Any
from uuid import UUID

import aio_pika
from aio_pika.abc import AbstractIncomingMessage

from core.audit import write_audit
from core.broker import RabbitBroker
from core.config import get_settings
from core.database import create_pool
from core.embeddings import EmbeddingService
from core.llm import LLMClient
from core.logging_config import configure_logging, request_id_ctx
from services.router_service import SemanticRouter, log_inference

logger = logging.getLogger("triage_worker")


class TriageWorker:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.broker = RabbitBroker(self.settings)
        self.pool = None
        self.embedder = None
        self.router = None
        self.llm = None
        self._running = False
        self._consumer_tag = None

    async def initialize(self) -> None:
        logger.info("Initializing TriageWorker...")
        self.pool = await create_pool(self.settings)
        await self.broker.connect()

        self.embedder = EmbeddingService(
            model_name=self.settings.embedding_model,
            expected_dim=self.settings.embedding_dim,
            device=self.settings.embedding_device,
            prefix=self.settings.resolved_embedding_prefix,
        )
        await asyncio.to_thread(self.embedder.load)

        self.llm = LLMClient(self.settings)
        self.router = SemanticRouter.from_settings(self.settings, self.llm)
        logger.info("TriageWorker initialized successfully.")

    async def run(self) -> None:
        self._running = True
        queue = self.broker.get_queue(self.settings.triage_queue)
        logger.info("Starting consumption on queue: %s", self.settings.triage_queue)

        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                if not self._running:
                    break
                await self.process_message(message)

    async def process_message(self, message: AbstractIncomingMessage) -> None:
        async with message.process(requeue=False, ignore_processed=True):
            headers = message.headers or {}
            retries = int(headers.get("x-retries", 0))
            req_id = headers.get("x-request-id", message.message_id or "-")
            request_id_ctx.set(str(req_id))

            try:
                payload = json.loads(message.body.decode("utf-8"))
                event_type = payload.get("event")
                ticket_id_str = payload.get("ticket_id")

                if not ticket_id_str or event_type != "ticket.created":
                    logger.warning("Ignoring invalid event payload: %s", payload)
                    return

                ticket_id = UUID(ticket_id_str)
                logger.info("Processing triage for ticket: %s (attempt: %d)", ticket_id, retries + 1)
                await self._process_ticket(ticket_id)
                logger.info("Successfully triaged ticket: %s", ticket_id)

            except Exception as exc:
                logger.exception("Failed processing message %s: %s", message.message_id, exc)
                await self._handle_failure(message, retries, str(exc))

    async def _process_ticket(self, ticket_id: UUID) -> None:
        assert self.pool is not None
        assert self.router is not None
        assert self.embedder is not None

        # Fetch ticket description
        async with self.pool.acquire() as conn:
            ticket = await conn.fetchrow(
                "SELECT id, description, category FROM tickets WHERE id = $1", ticket_id
            )
            if not ticket:
                logger.warning("Ticket %s not found in DB; dropping event", ticket_id)
                return

            # Also fetch embedding if available
            emb_row = await conn.fetchrow(
                "SELECT embedding FROM ticket_embeddings WHERE ticket_id = $1", ticket_id
            )
            embedding = emb_row["embedding"] if emb_row else None

        # Execute DistillMesh semantic routing
        routed = await self.router.infer(ticket["description"], embedding=embedding)
        prediction = routed.prediction

        # Update ticket in DB & log telemetry
        async with self.pool.acquire() as conn, conn.transaction():
            await conn.execute(
                """
                UPDATE tickets
                SET intent = $2,
                    category = COALESCE(category, $2),
                    priority = $3,
                    urgency_score = $4,
                    entities = $5,
                    triage_route = $6,
                    status = 'triaged'
                WHERE id = $1
                """,
                ticket_id,
                prediction.intent,
                prediction.priority,
                prediction.urgency,
                [e.model_dump() for e in prediction.entities],
                routed.route.value,
            )

            await log_inference(conn, routed, ticket_id=ticket_id)

            await write_audit(
                conn,
                entity_type="ticket",
                entity_id=ticket_id,
                action="ticket_triaged",
                actor=f"worker:{routed.route.value}",
                details={
                    "intent": prediction.intent,
                    "priority": prediction.priority,
                    "urgency": prediction.urgency,
                    "route": routed.route.value,
                    "model": routed.model_name,
                    "latency_ms": routed.latency_ms,
                },
            )

    async def _handle_failure(
        self,
        message: AbstractIncomingMessage,
        retries: int,
        error_msg: str,
    ) -> None:
        max_retries = self.settings.triage_max_retries
        headers = dict(message.headers or {})
        headers["x-retries"] = retries + 1
        headers["x-last-error"] = error_msg[:500]

        if retries < max_retries:
            logger.warning("Re-routing message to retry queue (delay=%dms, retry=%d/%d)",
                           self.settings.triage_retry_delay_ms, retries + 1, max_retries)
            await self.broker.publish_to_queue(
                self.settings.triage_retry_queue,
                body=message.body,
                headers=headers,
                message_id=message.message_id,
            )
        else:
            from middleware.resiliency import log_dlq_alert
            logger.error("Message exceeded max retries (%d). Sending to Dead Letter Queue (DLQ).", max_retries)
            ticket_id_str = headers.get("x-ticket-id") or str(message.message_id)
            log_dlq_alert(ticket_id=ticket_id_str, retries=retries + 1, error_msg=error_msg)
            await self.broker.publish_to_queue(
                self.settings.triage_dlq,
                body=message.body,
                headers=headers,
                message_id=message.message_id,
            )


    async def stop(self) -> None:
        logger.info("Stopping TriageWorker...")
        self._running = False
        await self.broker.close()
        if self.pool:
            await self.pool.close()
        if self.llm:
            await self.llm.aclose()
        logger.info("TriageWorker stopped.")


async def main() -> None:
    settings = get_settings()
    configure_logging(level=settings.log_level, json_logs=settings.json_logs)
    worker = TriageWorker()
    await worker.initialize()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda: asyncio.create_task(worker.stop()))
        except NotImplementedError:
            # Signal handling on Windows
            pass

    try:
        await worker.run()
    except asyncio.CancelledError:
        pass
    finally:
        await worker.stop()


if __name__ == "__main__":
    asyncio.run(main())
