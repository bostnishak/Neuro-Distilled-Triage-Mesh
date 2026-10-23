"""Distributed / Memory Token-Bucket Rate Limiter."""
from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from typing import Any, Callable

from fastapi import Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("rate_limiter")


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
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        if self.tokens >= amount:
            self.tokens -= amount
            return True
        return False


class RateLimiter:
    """Thread-safe per-client token bucket rate limiter."""

    def __init__(self, requests_per_minute: int = 180, burst: int = 30) -> None:
        self.rate = requests_per_minute / 60.0
        self.burst = float(burst)
        self.buckets: dict[str, TokenBucket] = defaultdict(
            lambda: TokenBucket(capacity=self.burst, refill_rate=self.rate)
        )
        self._lock = asyncio.Lock()

    async def is_allowed(self, client_id: str) -> bool:
        async with self._lock:
            if len(self.buckets) > 10000:
                self.buckets.clear()
            bucket = self.buckets[client_id]
            return bucket.consume(1.0)


class RateLimitingMiddleware(BaseHTTPMiddleware):
    """Enforces rate limiting on non-health API endpoints."""

    def __init__(self, app: Any, rate_limiter: RateLimiter | None = None) -> None:
        super().__init__(app)
        self.rate_limiter = rate_limiter or RateLimiter(requests_per_minute=180, burst=30)

    async def dispatch(self, request: Request, call_next: Callable[[Request], Any]) -> Response:
        endpoint = request.url.path
        if endpoint in ("/metrics", "/health", "/healthz", "/ready"):
            return await call_next(request)

        client_ip = request.client.host if request.client else "127.0.0.1"
        if not await self.rate_limiter.is_allowed(client_ip):
            logger.warning("Rate limit reached for client IP: %s on %s", client_ip, endpoint)
            return Response(
                content='{"detail": "Rate limit exceeded. Please throttle requests."}',
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                media_type="application/json",
                headers={"Retry-After": "2"},
            )

        return await call_next(request)
