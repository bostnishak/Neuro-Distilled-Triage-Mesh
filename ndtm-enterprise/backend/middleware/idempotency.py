"""Idempotency-Key replay protection with distributed Redis locking and body caching."""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Callable

import redis.asyncio as aioredis
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger("middleware.idempotency")
IDEMP_LOCK_TTL = 30
IDEMP_RESPONSE_TTL = 86400


class IdempotencyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: Any, redis_client: aioredis.Redis | None = None) -> None:
        super().__init__(app)
        self.redis = redis_client
        self._local_cache: dict[str, dict] = {}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Only inspect state-mutating requests
        if request.method not in ("POST", "PUT", "PATCH"):
            return await call_next(request)

        idemp_key = request.headers.get("Idempotency-Key")
        if not idemp_key:
            # If not provided, continue normally
            return await call_next(request)

        body_bytes = await request.body()
        body_hash = hashlib.sha256(body_bytes).hexdigest()
        cache_key = f"idemp:{idemp_key}"

        # 1. Redis lookup or local fallback
        if self.redis is not None:
            try:
                existing = await self.redis.get(cache_key)
                if existing:
                    data = json.loads(existing)
                    if data.get("status") == "IN_FLIGHT":
                        logger.warning("Concurrent in-flight duplicate detected for key %s", idemp_key)
                        return JSONResponse(
                            status_code=409,
                            content={
                                "error": "CONFLICT_IN_FLIGHT",
                                "message": "An identical request with this Idempotency-Key is currently processing.",
                            },
                        )
                    # Return cached response
                    return Response(
                        content=json.dumps(data["body"]).encode("utf-8"),
                        status_code=data["code"],
                        media_type="application/json",
                        headers={"X-Cache-Lookup": "HIT_IDEMPOTENT"},
                    )

                # Acquire atomic in-flight lock
                acquired = await self.redis.set(cache_key, json.dumps({"status": "IN_FLIGHT", "hash": body_hash}), nx=True, ex=IDEMP_LOCK_TTL)
                if not acquired:
                    return JSONResponse(
                        status_code=409,
                        content={"error": "CONFLICT_IN_FLIGHT", "message": "Concurrent request in-flight."},
                    )
            except Exception as exc:
                logger.warning("Redis idempotency error: %s", exc)

        # 2. Execute inner handler
        response = await call_next(request)

        # 3. Cache completed response if 2xx
        if 200 <= response.status_code < 300 and hasattr(response, "body"):
            try:
                resp_json = json.loads(response.body.decode("utf-8"))
                cache_payload = json.dumps({"status": "COMPLETED", "code": response.status_code, "body": resp_json})
                if self.redis:
                    await self.redis.setex(cache_key, IDEMP_RESPONSE_TTL, cache_payload)
                else:
                    self._local_cache[cache_key] = {"status": "COMPLETED", "code": response.status_code, "body": resp_json}
            except Exception as exc:
                logger.debug("Idempotency response cache update notice: %s", exc)

        return response
