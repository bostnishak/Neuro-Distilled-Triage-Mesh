"""Structured (JSON) logging with request-id correlation."""
from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime, timezone

#: Correlation id propagated through HTTP requests and RabbitMQ messages.
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")

_RESERVED_ATTRS = set(vars(logging.LogRecord("", 0, "", 0, "", None, None)).keys()) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    """Render log records as single-line JSON documents (ELK / Loki friendly)."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_ctx.get(),
        }
        # Anything passed through `extra={...}` becomes a top-level field.
        for key, value in record.__dict__.items():
            if key not in _RESERVED_ATTRS and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


class _ContextTextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        record.request_id = request_id_ctx.get()
        return super().format(record)


def configure_logging(level: str = "INFO", json_logs: bool = True) -> None:
    """Install a single stdout handler on the root logger."""
    handler = logging.StreamHandler(sys.stdout)
    if json_logs:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            _ContextTextFormatter("%(asctime)s %(levelname)-8s [%(request_id)s] %(name)s: %(message)s")
        )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    for noisy in ("aio_pika", "aiormq", "httpx", "httpcore", "urllib3", "sentence_transformers"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
