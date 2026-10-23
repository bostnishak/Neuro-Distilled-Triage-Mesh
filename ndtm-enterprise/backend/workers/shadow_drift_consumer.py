"""Asynchronous shadow drift evaluator worker consuming q.shadow.evaluate."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import numpy as np
from aio_pika.abc import AbstractIncomingMessage

from backend.core.logging import setup_enterprise_logging
from backend.services.shadow_evaluator import ShadowEvaluatorService
from backend.services.websocket_manager import ws_manager
from backend.workers.rabbitmq_client import RabbitMQClient

setup_enterprise_logging("INFO")
logger = logging.getLogger("workers.shadow_consumer")

evaluator = ShadowEvaluatorService()


async def handle_shadow_evaluation(payload: dict[str, Any], message: AbstractIncomingMessage) -> None:
    request_id = payload.get("request_id", "unknown")
    input_text = payload.get("text", "")
    student_intent = payload.get("student_intent", "GENERAL")
    student_conf = float(payload.get("student_confidence", 0.5))
    probs = np.array(payload.get("probs", [0.125] * 8), dtype=np.float32)

    logger.info("Evaluating shadow drift for request %s...", request_id)
    await evaluator.evaluate_async(
        request_id=request_id,
        input_text=input_text,
        student_intent=student_intent,
        student_confidence=student_conf,
        student_probs=probs,
    )

    # Broadcast telemetry update to UI
    await ws_manager.broadcast_event(
        "shadow_evaluation_completed",
        {"request_id": request_id, "student_intent": student_intent, "status": "processed"},
    )


async def main() -> None:
    client = RabbitMQClient()
    await client.connect()
    logger.info("Shadow Drift Consumer Worker started.")
    try:
        await client.consume_queue("q.shadow.evaluate", handle_shadow_evaluation)
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
