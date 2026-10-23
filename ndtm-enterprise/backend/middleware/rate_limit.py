"""Atomic Redis Lua sliding-window rate limiter with burst protection and fallback."""
from __future__ import annotations

import logging
import time
from typing import Callable

import redis.asyncio as aioredis
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from backend.core.config import get_settings

logger = logging.getLogger("middleware.rate_limit")
settings = get_settings()

# Atomic Lua Script for sliding window rate limiting
SLIDING_WINDOW_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local clear_before = now - window

redis.call('ZREMRANGEBYSCORE', key, 0, clear_before)
local current_requests = redis.call('ZCARD', key)

if current_requests < limit then
    redis.call('ZADD', key, now, now .. '-' .. math.random(1000, 9999))
    redis.call('EXPIRE', key, math.ceil(window))
    return {1, limit - current_requests - 1, 0}
else
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    local retry_after = 1
    if #oldest > 0 then
        retry_after = math.ceil((tonumber(oldest[2]) + window) - now)
    end
    return {0, 0, math.max(1, retry_after)}
end
"""


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: Any, redis_client: aioredis.Redis | None = None) -> None:
        super().__init__(app)
        self.redis = redis_client
        self._local_memory_fallback: dict[str, list[float]] = {}

    def _get_client_key(self, request: Request) -> str:
        # User ID if authenticated or Client IP
        forwarded = request.headers.get("X-Forwarded-For")
        client_ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "127.0.0.1")
        return f"rl:window:{client_ip}"

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.url.path in ("/metrics", "/health", "/healthz", "/docs", "/openapi.json"):
            return await call_next(request)

        key = self._get_client_key(request)
        now = time.time()
        window_seconds = 60.0
        limit = settings.RATE_LIMIT_PER_MINUTE

        allowed = True
        remaining = limit
        retry_after = 0

        if self.redis is not None:
            try:
                res = await self.redis.eval(SLIDING_WINDOW_LUA, 1, key, now, window_seconds, limit)
                allowed = bool(res[0])
                remaining = int(res[1])
                retry_after = int(res[2])
            except Exception as exc:
                logger.warning("Redis rate limiter error: %s. Using local fallback.", exc)
                allowed, remaining, retry_after = self._fallback_check(key, now, window_seconds, limit)
        else:
            allowed, remaining, retry_after = self._fallback_check(key, now, window_seconds, limit)

        if not allowed:
            logger.warning("Rate limit exceeded for %s. Retry after %ds", key, retry_after)
            return JSONResponse(
                status_code=429,
                content={
                    "error": "TOO_MANY_REQUESTS",
                    "message": "Rate limit quota exceeded. Please throttle your requests.",
                    "retry_after_seconds": retry_after,
                },
                headers={"Retry-After": str(retry_after), "X-RateLimit-Remaining": "0"},
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(max(0, remaining))
        return response

    def _fallback_check(self, key: str, now: float, window: float, limit: int) -> tuple[bool, int, int]:
        timestamps = self._local_memory_fallback.setdefault(key, [])
        # Prune old timestamps
        cutoff = now - window
        self._local_memory_fallback[key] = [t for t in timestamps if t > cutoff]
        current_count = len(self._local_memory_fallback[key])

        if current_count < limit:
            self._local_memory_fallback[key].append(now)
            return True, limit - current_count - 1, 0
        else:
            oldest = self._local_memory_fallback[key][0]
            retry_after = max(1, int(oldest + window - now))
            return False, 0, retry_after
