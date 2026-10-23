"""Circuit Breaker Pattern protecting external API and Teacher LLM calls."""
from __future__ import annotations

import asyncio
import logging
import time
from enum import Enum
from typing import Any, Callable

try:
    from ndtm_platform.middleware.telemetry import REGISTRY
    CIRCUIT_BREAKER_STATE = REGISTRY.circuit_breaker_state
except Exception:
    CIRCUIT_BREAKER_STATE = None

logger = logging.getLogger("circuit_breaker")


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerOpenError(Exception):
    """Raised when an operation is attempted while the circuit is tripped."""


CircuitBreakerOpenException = CircuitBreakerOpenError


class CircuitBreaker:
    """State machine preventing cascading failure during upstream outages."""

    def __init__(
        self,
        name: str = "teacher_llm",
        failure_threshold: int = 3,
        recovery_timeout: float = 30.0,
        recovery_time: float | None = None,
        half_open_success_threshold: int = 1,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_time if recovery_time is not None else recovery_timeout
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
        if CIRCUIT_BREAKER_STATE is not None:
            val = 0.0
            if self._state == CircuitState.HALF_OPEN:
                val = 1.0
            elif self._state == CircuitState.OPEN:
                val = 2.0
            try:
                CIRCUIT_BREAKER_STATE.labels(service=self.name).set(val)
            except Exception:
                pass

    async def call(self, coro_func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute async function guarded by circuit state."""
        async with self._lock:
            if self._state == CircuitState.OPEN:
                assert self._tripped_at is not None
                if time.monotonic() - self._tripped_at >= self.recovery_timeout:
                    logger.info("CircuitBreaker [%s] recovery timeout elapsed -> HALF_OPEN.", self.name)
                    self._state = CircuitState.HALF_OPEN
                    self._consecutive_successes = 0
                    self._sync_metric()
                else:
                    raise CircuitBreakerOpenError(f"CircuitBreaker [{self.name}] is OPEN. Call blocked.")

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
                    logger.info("CircuitBreaker [%s] probe passed -> CLOSED.", self.name)
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
                self.name,
                self._consecutive_failures,
                self.failure_threshold,
                exc,
            )
            if self._consecutive_failures >= self.failure_threshold:
                self._state = CircuitState.OPEN
                self._tripped_at = time.monotonic()
                self._sync_metric()
                logger.error("CircuitBreaker [%s] TRIPPED to OPEN for %.1fs.", self.name, self.recovery_timeout)
