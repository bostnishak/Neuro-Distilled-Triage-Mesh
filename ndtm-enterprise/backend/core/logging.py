"""High-throughput JSON structured logging with contextual distributed trace identifiers."""
from __future__ import annotations

import contextvars
import json
import logging
import sys
from datetime import datetime, timezone

# Thread/coroutine-safe context variables for distributed correlation
request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")
user_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("user_id", default="anonymous")


class JSONLogFormatter(logging.Formatter):
    """Outputs standardized single-line JSON log events for Datadog, Prometheus, or ELK."""

    def format(self, record: logging.LogRecord) -> str:
        log_payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_ctx.get(),
            "user_id": user_id_ctx.get(),
        }
        if record.exc_info:
            log_payload["stack_trace"] = self.formatException(record.exc_info)
        if hasattr(record, "extra_fields"):
            log_payload.update(record.extra_fields)

        return json.dumps(log_payload, ensure_ascii=False)


def setup_enterprise_logging(level: str = "INFO") -> None:
    """Configures root logger with single-line JSON formatter and suppresses noisy loggers."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONLogFormatter())

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(level.upper())

    # Suppress verbose dependency logs
    for noisy in ("uvicorn.access", "httpx", "httpcore", "aio_pika", "aiormq", "passlib"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
