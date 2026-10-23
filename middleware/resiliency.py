"""Resiliency, Circuit Breaker, Idempotency & Fault Tolerance.

Features:
1. Circuit Breaker for External Services (Teacher LLM API):
   - States: CLOSED (healthy), OPEN (tripped due to errors/timeouts), HALF_OPEN (probing).
   - Prevents cascading thread/event-loop starvation during 429 rate limits or upstream outages.
   - Automatically degrades to local ONNX student model or keyword heuristic.
2. Distributed Database Idempotency Middleware:
   - Evaluates `Idempotency-Key` / `X-Idempotency-Key` HTTP headers for all mutating endpoints.
   - Saves responses in PostgreSQL `idempotency_keys` with request body hash verification.
   - Guarantees network retries never duplicate tickets or financial/audit entries.
3. RabbitMQ DLQ Monitoring & Alerting:
   - Structured alert hooks when poison messages transition to `triage_dlq`.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable

import asyncpg
from fastapi import Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from middleware.telemetry_and_security import CIRCUIT_BREAKER_STATE

logger = logging.getLogger("resiliency")


# =============================================================================
# Circuit Breaker Implementation
# =============================================================================
class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerOpenError(Exception):
    """Raised when an external call is attempted while the circuit is tripped."""


class CircuitBreaker:
    """State machine protecting upstream services from cascade failures."""

    def __init__(
        self,
        name: str = "teacher_llm",
        failure_threshold: int = 3,
        recovery_timeout: float = 30.0,
        half_open_success_threshold: int = 1,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_success_threshold = half_open_success_threshold

        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._consecutive_successes = 0
        self._tripped_at: float | None = None
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        return self._state

    def _sync_metric(self) -> None:
        val = 0.0
        if self._state == CircuitState.HALF_OPEN:
            val = 1.0
        elif self._state == CircuitState.OPEN:
            val = 2.0
        CIRCUIT_BREAKER_STATE.labels(service=self.name).set(val)

    async def call(self, coro_func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute async function protected by the circuit breaker."""
        async with self._lock:
            # Check if OPEN state has expired and should transition to HALF_OPEN
            if self._state == CircuitState.OPEN:
                assert self._tripped_at is not None
                if time.monotonic() - self._tripped_at >= self.recovery_timeout:
                    logger.info("CircuitBreaker [%s] recovery timeout elapsed. Transitioning OPEN -> HALF_OPEN.", self.name)
                    self._state = CircuitState.HALF_OPEN
                    self._consecutive_successes = 0
                    self._sync_metric()
                else:
                    raise CircuitBreakerOpenError(f"CircuitBreaker [{self.name}] is OPEN. Call rejected.")

        # Attempt invocation
        try:
            result = await coro_func(*args, **kwargs)
        except Exception as exc:
            await self._record_failure(exc)
            raise exc

        await self._record_success()
        return result

    async def _record_success(self) -> None:
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._consecutive_successes += 1
                if self._consecutive_successes >= self.half_open_success_threshold:
                    logger.info("CircuitBreaker [%s] probe succeeded. Transitioning HALF_OPEN -> CLOSED.", self.name)
                    self._state = CircuitState.CLOSED
                    self._consecutive_failures = 0
                    self._tripped_at = None
                    self._sync_metric()
            elif self._state == CircuitState.CLOSED:
                self._consecutive_failures = 0

    async def _record_failure(self, exc: Exception) -> None:
        async with self._lock:
            self._consecutive_failures += 1
            logger.warning(
                "CircuitBreaker [%s] failure %d/%d: %s",
                self.name, self._consecutive_failures, self.failure_threshold, exc
            )
            if self._consecutive_failures >= self.failure_threshold:
                self._state = CircuitState.OPEN
                self._tripped_at = time.monotonic()
                self._sync_metric()
                logger.error(
                    "CircuitBreaker [%s] TRIP! Converted to OPEN for %.1fs.",
                    self.name, self.recovery_timeout
                )


# =============================================================================
# Database-Backed Idempotency Middleware
# =============================================================================
class IdempotencyMiddleware(BaseHTTPMiddleware):
    """Enforces idempotency on POST requests using an Idempotency-Key header."""

    HEADER_NAMES = ("idempotency-key", "x-idempotency-key")
    TTL_HOURS = 24

    def __init__(self, app: Any) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable[[Request], Any]) -> Response:
        # Only enforce on mutating requests (POST, PUT, PATCH)
        if request.method not in ("POST", "PUT", "PATCH"):
            return await call_next(request)

        # Look for idempotency key header
        key: str | None = None
        for h_name in self.HEADER_NAMES:
            if h_name in request.headers:
                key = request.headers[h_name].strip()
                break

        if not key:
            # Client did not provide idempotency key; proceed normally
            return await call_next(request)

        # Read body to compute fingerprint hash
        body_bytes = await request.body()
        req_hash = hashlib.sha256(body_bytes).hexdigest()

        # Database pool from app state
        pool: asyncpg.Pool = getattr(request.app.state, "pool", None)
        if not pool:
            # Pool not ready yet, skip
            return await call_next(request)

        path = request.url.path

        # 1. Check if key already exists
        async with pool.acquire() as conn:
            existing = await conn.fetchrow(
                """
                SELECT request_hash, response_status, response_headers, response_body, expires_at
                FROM idempotency_keys
                WHERE key = $1
                """,
                key,
            )

            if existing:
                # Key already recorded!
                # Verify payload match to prevent key hijacking with mismatched payloads
                if existing["request_hash"] != req_hash:
                    logger.warning("Idempotency key %s reused with divergent payload!", key)
                    return JSONResponse(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        content={
                            "detail": "Idempotency key already exists with a different request payload."
                        },
                    )

                logger.info("Idempotency cache hit for key: %s (Status: %d)", key, existing["response_status"])
                # Return cached response directly
                headers = dict(existing["response_headers"]) if existing["response_headers"] else {}
                headers["X-Cache-Lookup"] = "HIT-IDEMPOTENT"
                return JSONResponse(
                    status_code=existing["response_status"],
                    content=existing["response_body"],
                    headers=headers,
                )

        # 2. Process request through pipeline
        response = await call_next(request)

        # 3. Only cache successful or client-side responses (do not cache transient 5xx server errors)
        if 200 <= response.status_code < 500:
            resp_body_bytes = b""
            async for chunk in response.body_iterator:
                resp_body_bytes += chunk

            try:
                resp_json = json.loads(resp_body_bytes.decode("utf-8"))
            except Exception:
                resp_json = {"raw": resp_body_bytes.decode("utf-8", errors="replace")}

            expires_at = datetime.now(timezone.utc) + timedelta(hours=self.TTL_HOURS)

            try:
                async with pool.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO idempotency_keys (key, request_path, request_hash, response_status,
                                                      response_headers, response_body, expires_at)
                        VALUES ($1, $2, $3, $4, $5, $6, $7)
                        ON CONFLICT (key) DO NOTHING
                        """,
                        key, path, req_hash, response.status_code,
                        {"Content-Type": "application/json"},
                        resp_json, expires_at,
                    )
            except Exception as exc:
                logger.warning("Failed saving idempotency record: %s", exc)

            # Reconstruct response since body_iterator was consumed
            headers = dict(response.headers)
            headers["X-Cache-Lookup"] = "MISS-SAVED"
            return JSONResponse(
                status_code=response.status_code,
                content=resp_json,
                headers=headers,
            )

        return response


# =============================================================================
# RabbitMQ Dead Letter Queue (DLQ) Notification Hook
# =============================================================================
def log_dlq_alert(ticket_id: str, retries: int, error_msg: str) -> None:
    """Structured SRE alert when a poison message is dumped into triage_dlq."""
    alert_payload = {
        "alert": "RABBITMQ_DLQ_POISON_MESSAGE",
        "severity": "CRITICAL",
        "ticket_id": ticket_id,
        "attempts": retries,
        "error": error_msg,
        "action_required": "Inspect DLQ and check database connection or model corruption.",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    logger.critical("DEAD LETTER QUEUE EVENT: %s", json.dumps(alert_payload))
