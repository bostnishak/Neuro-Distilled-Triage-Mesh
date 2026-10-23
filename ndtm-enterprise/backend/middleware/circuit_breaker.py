"""Stateful Circuit Breaker pattern guarding upstream Teacher LLM integrations."""
from __future__ import annotations

import asyncio
import logging
import time
from enum import Enum
from typing import Any, Callable

from backend.core.exceptions import CircuitBreakerOpenError

logger = logging.getLogger("middleware.circuit_breaker")


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreaker:
    """Finite State Machine guarding external API calls from cascading failure."""

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

    def force_state(self, new_state: CircuitState) -> None:
        """Chaos injection hook to deliberately trip or reset the circuit breaker."""
        self._state = new_state
        if new_state == CircuitState.OPEN:
            self._tripped_at = time.monotonic()
        logger.info("CircuitBreaker [%s] forced to %s", self.name, new_state.value)

    async def call(self, coro_func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Executes an async callable guarded by the current circuit state."""
        async with self._lock:
            if self._state == CircuitState.OPEN:
                assert self._tripped_at is not None
                if time.monotonic() - self._tripped_at >= self.recovery_timeout:
                    logger.info("CircuitBreaker [%s] recovery timeout elapsed -> HALF_OPEN.", self.name)
                    self._state = CircuitState.HALF_OPEN
                    self._consecutive_successes = 0
                else:
                    raise CircuitBreakerOpenError(
                        f"CircuitBreaker [{self.name}] is OPEN. External call rejected."
                    )

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
                logger.error(
                    "CircuitBreaker [%s] TRIPPED to OPEN for %.1fs recovery window.",
                    self.name,
                    self.recovery_timeout,
                )
