"""Observability, Prometheus Metrics & Distributed Request-ID Telemetry."""
from __future__ import annotations

import contextvars
import json
import logging
import sys
import time
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

from fastapi import Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware

# Context variable for distributed request-id tracing
request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

logger = logging.getLogger("telemetry")


# =============================================================================
# Prometheus Metrics Registry
# =============================================================================
HTTP_REQUESTS_TOTAL = Counter(
    "mesh_http_requests_total",
    "Total HTTP requests received",
    ["method", "endpoint", "status_code"],
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "mesh_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

ONNX_INFERENCE_DURATION_SECONDS = Histogram(
    "mesh_onnx_inference_duration_seconds",
    "Execution time of ONNX student model in seconds",
    ["model_name"],
    buckets=[0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1],
)

ROUTER_INFERENCES_TOTAL = Counter(
    "mesh_router_inferences_total",
    "Total triage inferences routed by target",
    ["route", "intent"],
)

ROUTER_CACHE_HITS_TOTAL = Counter(
    "mesh_router_cache_hits_total",
    "Distributed semantic cache hits vs misses",
    ["status"],
)

CIRCUIT_BREAKER_STATE = Gauge(
    "mesh_circuit_breaker_state",
    "State of Teacher LLM circuit breaker (0=Closed, 1=Half-Open, 2=Open)",
    ["service"],
)

SHADOW_DIVERGENCE_HISTOGRAM = Histogram(
    "mesh_shadow_divergence_score",
    "Semantic divergence score between Student and Teacher LLM (0.0=Identical, 1.0=Divergent)",
    buckets=[0.0, 0.1, 0.2, 0.3, 0.5, 0.7, 0.9, 1.0],
)


class PrometheusRegistryHolder:
    http_requests = HTTP_REQUESTS_TOTAL
    http_duration = HTTP_REQUEST_DURATION_SECONDS
    onnx_duration = ONNX_INFERENCE_DURATION_SECONDS
    router_inferences = ROUTER_INFERENCES_TOTAL
    cache_hits = ROUTER_CACHE_HITS_TOTAL
    circuit_breaker_state = CIRCUIT_BREAKER_STATE
    shadow_divergence = SHADOW_DIVERGENCE_HISTOGRAM


REGISTRY = PrometheusRegistryHolder()


# =============================================================================
# JSON Structured Log Formatter
# =============================================================================
class JSONLogFormatter(logging.Formatter):
    """Formats log records as JSON with correlation ID and timestamp."""

    def format(self, record: logging.LogRecord) -> str:
        log_payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_ctx.get(),
        }
        if record.exc_info:
            log_payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_payload, ensure_ascii=False)


def setup_structured_logging(level: str = "INFO") -> None:
    """Configure root logger to write single-line JSON to stdout."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONLogFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    for noisy in ("uvicorn.access", "httpx", "httpcore", "aio_pika", "aiormq"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


# =============================================================================
# Telemetry Middleware
# =============================================================================
class TelemetryMiddleware(BaseHTTPMiddleware):
    """Extracts/injects X-Request-ID, calculates latency, and records Prometheus metrics."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Any]) -> Response:
        req_id = request.headers.get("X-Request-ID") or uuid4().hex
        token = request_id_ctx.set(req_id)
        start_time = time.perf_counter()

        endpoint = request.url.path
        status_code = 500

        try:
            response: Response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = req_id
            return response
        finally:
            elapsed = time.perf_counter() - start_time
            request_id_ctx.reset(token)

            # Record Prometheus Metrics (excluding health probes from histograms)
            if endpoint not in ("/metrics", "/health", "/healthz"):
                HTTP_REQUESTS_TOTAL.labels(
                    method=request.method,
                    endpoint=endpoint,
                    status_code=str(status_code),
                ).inc()

                HTTP_REQUEST_DURATION_SECONDS.labels(
                    method=request.method,
                    endpoint=endpoint,
                ).observe(elapsed)


RequestCorrelationMiddleware = TelemetryMiddleware


def get_prometheus_metrics_response() -> Response:
    """Generate Prometheus exposition format payload."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
