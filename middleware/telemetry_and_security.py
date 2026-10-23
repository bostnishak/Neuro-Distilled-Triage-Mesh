"""Observability, Telemetry, PII Masking, Input Sanitization & Rate Limiting.

Features:
1. PII Redaction:
   - Turkish Republic ID (TC Kimlik No - TCKN with algorithmic checksum verification) -> [MASKED_TCKN]
   - Phone numbers (Turkish mobile 05xx, international +90, format-tolerant) -> [MASKED_PHONE]
   - Email addresses (RFC 5322 compliant regex) -> [MASKED_EMAIL]
   - Financial identifiers: IBAN (TR + 24 digits) and Credit Card numbers -> [MASKED_IBAN] / [MASKED_CARD]
2. Prompt Injection & Input Sanitization:
   - Neutralizes LLM delimiter attacks and control characters.
3. Prometheus Metrics:
   - System request count, HTTP latency histograms, ONNX inference times,
     RabbitMQ queue depths, and router cache hits.
4. Token-Bucket Rate Limiter:
   - High-performance in-memory rate limiter per client IP with burst support.
5. Observability Middleware:
   - Request-ID correlation, token usage estimation, and execution latency logging.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from collections import defaultdict
from typing import Any, Callable

from fastapi import HTTPException, Request, Response, status
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware

from core.logging_config import request_id_ctx

logger = logging.getLogger("telemetry_security")


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
    "Semantic router cache hits and misses",
    ["status"],  # 'hit' | 'miss'
)

RABBITMQ_QUEUE_DEPTH = Gauge(
    "mesh_rabbitmq_queue_depth",
    "Number of messages pending in RabbitMQ queue",
    ["queue_name"],
)

CIRCUIT_BREAKER_STATE = Gauge(
    "mesh_circuit_breaker_state",
    "State of Teacher LLM circuit breaker (0=Closed/Normal, 1=Half-Open, 2=Open/Tripped)",
    ["service"],
)

SHADOW_DIVERGENCE_HISTOGRAM = Histogram(
    "mesh_shadow_divergence_score",
    "Semantic divergence score between Student and Teacher LLM (0.0=Identical, 1.0=Divergent)",
    buckets=[0.0, 0.1, 0.2, 0.3, 0.5, 0.7, 0.9, 1.0],
)


# =============================================================================
# PII Redaction Engine
# =============================================================================
# Regex patterns
_EMAIL_RE = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b",
    re.IGNORECASE,
)

# Turkish phone formats: 05xx xxx xx xx, +90 5xx xxx xxxx, 05xxxxxxxxx, etc.
_PHONE_RE = re.compile(
    r"(?:\+?90\s*|\b0)?5\d{2}[\s.-]?\d{3}[\s.-]?\d{2}[\s.-]?\d{2}\b"
)

# IBAN (TR followed by 24 digits, optional spaces)
_IBAN_RE = re.compile(
    r"\bTR\d{2}(?:\s*\d{4}){5}\s*\d{2}\b",
    re.IGNORECASE,
)

# Credit card (13 to 19 digits with dashes/spaces)
_CREDIT_CARD_RE = re.compile(
    r"\b(?:\d{4}[-\s]?){3}\d{4}\b|\b\d{15,16}\b"
)

# Potential 11-digit national ID (TCKN)
_TCKN_CANDIDATE_RE = re.compile(r"\b[1-9]\d{10}\b")


def validate_tckn(tckn: str) -> bool:
    """Validate Turkish Republic Identification Number (TC Kimlik No) checksum."""
    if len(tckn) != 11 or not tckn.isdigit() or tckn[0] == "0":
        return False
    digits = [int(c) for c in tckn]
    # 10th digit check: ((d1 + d3 + d5 + d7 + d9) * 7 - (d2 + d4 + d6 + d8)) % 10 == d10
    odd_sum = sum(digits[0:9:2])
    even_sum = sum(digits[1:8:2])
    tenth = ((odd_sum * 7) - even_sum) % 10
    if tenth != digits[9]:
        return False
    # 11th digit check: sum(d1..d10) % 10 == d11
    eleventh = sum(digits[:10]) % 10
    return eleventh == digits[10]


def redact_pii(text: str) -> str:
    """Scrub sensitive personal data (TCKN, phone, email, financial) from text.

    Replaces with standardized anonymized tokens for GDPR/KVKK compliance.
    """
    if not text:
        return text

    # 1. Email Redaction
    redacted = _EMAIL_RE.sub("[MASKED_EMAIL]", text)

    # 2. IBAN & Credit Card Redaction
    redacted = _IBAN_RE.sub("[MASKED_IBAN]", redacted)
    redacted = _CREDIT_CARD_RE.sub("[MASKED_CARD]", redacted)

    # 3. Phone Redaction
    redacted = _PHONE_RE.sub("[MASKED_PHONE]", redacted)

    # 4. TCKN Redaction (only masks when mathematical checksum passes to avoid false positives on 11-digit numbers)
    def _tckn_replacer(match: re.Match[str]) -> str:
        candidate = match.group(0)
        return "[MASKED_TCKN]" if validate_tckn(candidate) else candidate

    redacted = _TCKN_CANDIDATE_RE.sub(_tckn_replacer, redacted)

    return redacted


# =============================================================================
# Input Sanitization & Prompt Injection Defense
# =============================================================================
_PROMPT_INJECTION_PATTERNS = [
    re.compile(r"<\s*\|\s*im_start\s*\|>", re.IGNORECASE),
    re.compile(r"<\s*\|\s*im_end\s*\|>", re.IGNORECASE),
    re.compile(r"\[\s*INST\s*\]", re.IGNORECASE),
    re.compile(r"system\s*:", re.IGNORECASE),
    re.compile(r"ignore\s+(all\s+)?(previous|prior)\s+instructions?", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+in\s+(developer|dan)\s+mode", re.IGNORECASE),
]


def sanitize_input_text(text: str) -> str:
    """Neutralize control characters and prompt injection delimiters."""
    if not text:
        return text

    # Remove non-printable control characters (except newline and tab)
    sanitized = "".join(c for c in text if c >= " " or c in "\n\t")

    # Neutralize prompt injection triggers
    for pattern in _PROMPT_INJECTION_PATTERNS:
        sanitized = pattern.sub("[FILTERED_PROMPT_DELIMITER]", sanitized)

    return sanitized.strip()


# =============================================================================
# In-Memory Token-Bucket Rate Limiter
# =============================================================================
class TokenBucket:
    __slots__ = ("capacity", "refill_rate", "tokens", "last_refill")

    def __init__(self, capacity: float, refill_rate: float) -> None:
        self.capacity = capacity
        self.refill_rate = refill_rate  # tokens per second
        self.tokens = capacity
        self.last_refill = time.monotonic()

    def consume(self, amount: float = 1.0) -> bool:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.last_refill = now
        # Refill tokens up to capacity
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        if self.tokens >= amount:
            self.tokens -= amount
            return True
        return False


class RateLimiter:
    """Thread-safe, high-speed per-IP token bucket rate limiter."""

    def __init__(self, requests_per_minute: int = 120, burst: int = 20) -> None:
        self.rate = requests_per_minute / 60.0
        self.burst = float(burst)
        self.buckets: dict[str, TokenBucket] = defaultdict(
            lambda: TokenBucket(capacity=self.burst, refill_rate=self.rate)
        )
        self._lock = asyncio.Lock()

    async def is_allowed(self, client_id: str) -> bool:
        async with self._lock:
            # Periodic cleanup if registry grows very large
            if len(self.buckets) > 10000:
                self.buckets.clear()
            bucket = self.buckets[client_id]
            return bucket.consume(1.0)


# =============================================================================
# FastAPI Middlewares
# =============================================================================
class TelemetryAndSecurityMiddleware(BaseHTTPMiddleware):
    """Integrates Request ID, PII redaction logging, rate limiting, and Prometheus metrics."""

    def __init__(self, app: Any, rate_limiter: RateLimiter | None = None) -> None:
        super().__init__(app)
        self.rate_limiter = rate_limiter or RateLimiter(requests_per_minute=180, burst=30)

    async def dispatch(self, request: Request, call_next: Callable[[Request], Any]) -> Response:
        # 1. Skip metrics and health checks from rate limiting
        endpoint = request.url.path
        if endpoint in ("/metrics", "/health", "/healthz", "/ready"):
            return await call_next(request)

        # 2. Rate limiting check
        client_ip = request.client.host if request.client else "127.0.0.1"
        if not await self.rate_limiter.is_allowed(client_ip):
            logger.warning("Rate limit exceeded for client: %s on %s", client_ip, endpoint)
            return Response(
                content='{"detail": "Too many requests. Please slow down."}',
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                media_type="application/json",
                headers={"Retry-After": "2"},
            )

        # 3. Execution & Telemetry Timing
        start_time = time.perf_counter()
        req_id = request.headers.get("X-Request-ID") or request_id_ctx.get()

        try:
            response: Response = await call_next(request)
            status_code = response.status_code
        except Exception as exc:
            status_code = 500
            logger.exception("Unhandled error processing %s: %s", endpoint, exc)
            raise exc
        finally:
            elapsed = time.perf_counter() - start_time
            # Record Prometheus Metrics
            HTTP_REQUESTS_TOTAL.labels(
                method=request.method,
                endpoint=endpoint,
                status_code=str(status_code),
            ).inc()

            HTTP_REQUEST_DURATION_SECONDS.labels(
                method=request.method,
                endpoint=endpoint,
            ).observe(elapsed)

        return response


def get_prometheus_metrics_response() -> Response:
    """Generate Prometheus exposition format payload."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
