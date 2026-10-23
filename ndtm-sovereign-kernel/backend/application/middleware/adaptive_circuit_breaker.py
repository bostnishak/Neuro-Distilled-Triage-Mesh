import time
from enum import Enum
from typing import Callable, Any, Optional
from core.exceptions import CircuitBreakerOpenException
from core.logging_otel import logger, CIRCUIT_BREAKER_STATE


class CircuitState(Enum):
    CLOSED = 0
    HALF_OPEN = 1
    OPEN = 2


class AdaptiveCircuitBreaker:
    """Adaptive three-state circuit breaker with sliding window and metrics telemetry."""

    def __init__(
        self,
        service_name: str,
        failure_threshold_ratio: float = 0.5,
        window_size: int = 20,
        recovery_timeout_seconds: float = 15.0,
        half_open_success_threshold: int = 3,
    ):
        self.service_name = service_name
        self.failure_threshold_ratio = failure_threshold_ratio
        self.window_size = window_size
        self.recovery_timeout_seconds = recovery_timeout_seconds
        self.half_open_success_threshold = half_open_success_threshold

        self.state = CircuitState.CLOSED
        self.window: list[bool] = []  # True = success, False = failure
        self.opened_at: Optional[float] = None
        self.half_open_successes = 0

        self._update_metrics()

    def _update_metrics(self) -> None:
        CIRCUIT_BREAKER_STATE.labels(service_name=self.service_name).set(self.state.value)

    def can_execute(self) -> bool:
        now = time.time()
        if self.state == CircuitState.OPEN:
            assert self.opened_at is not None
            if now - self.opened_at >= self.recovery_timeout_seconds:
                self.state = CircuitState.HALF_OPEN
                self.half_open_successes = 0
                self._update_metrics()
                logger.info("circuit_breaker_transition_half_open", service=self.service_name)
                return True
            return False
        return True

    def record_success(self) -> None:
        if self.state == CircuitState.HALF_OPEN:
            self.half_open_successes += 1
            if self.half_open_successes >= self.half_open_success_threshold:
                self.state = CircuitState.CLOSED
                self.window.clear()
                self._update_metrics()
                logger.info("circuit_breaker_recovered_closed", service=self.service_name)
        else:
            self.window.append(True)
            if len(self.window) > self.window_size:
                self.window.pop(0)

    def record_failure(self) -> None:
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
            self.opened_at = time.time()
            self._update_metrics()
            logger.warning("circuit_breaker_reopened_from_half_open", service=self.service_name)
        else:
            self.window.append(False)
            if len(self.window) > self.window_size:
                self.window.pop(0)

            # Check threshold
            if len(self.window) >= 5:  # Minimum sample size before tripping
                failure_count = self.window.count(False)
                ratio = failure_count / len(self.window)
                if ratio >= self.failure_threshold_ratio:
                    self.state = CircuitState.OPEN
                    self.opened_at = time.time()
                    self._update_metrics()
                    logger.error(
                        "circuit_breaker_tripped_open",
                        service=self.service_name,
                        failure_ratio=ratio,
                        threshold=self.failure_threshold_ratio,
                    )

    async def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Executes async callable guarded by the circuit breaker."""
        if not self.can_execute():
            assert self.opened_at is not None
            remaining = self.recovery_timeout_seconds - (time.time() - self.opened_at)
            raise CircuitBreakerOpenException(self.service_name, max(0.1, remaining))

        try:
            result = await func(*args, **kwargs)
            self.record_success()
            return result
        except Exception as e:
            self.record_failure()
            raise e
