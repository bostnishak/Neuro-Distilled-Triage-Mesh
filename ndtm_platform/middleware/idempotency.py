"""Database-backed Idempotency Middleware for network replay protection."""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Callable

import asyncpg
from fastapi import Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger("idempotency")


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """Enforces idempotency on POST requests using an Idempotency-Key header."""

    HEADER_NAMES = ("idempotency-key", "x-idempotency-key")

    async def dispatch(self, request: Request, call_next: Callable[[Request], Any]) -> Response:
        if request.method not in ("POST", "PUT", "PATCH"):
            return await call_next(request)

        key: str | None = None
        for h_name in self.HEADER_NAMES:
            if h_name in request.headers:
                key = request.headers[h_name].strip()
                break

        if not key:
            return await call_next(request)

        pool: asyncpg.Pool = getattr(request.app.state, "pool", None)
        if not pool:
            return await call_next(request)

        # 1. Check if key is already processed
        async with pool.acquire() as conn:
            existing = await conn.fetchrow(
                "SELECT response_payload FROM idempotency_keys WHERE key = $1", key
            )
            if existing:
                logger.info("Idempotency hit for key: %s", key)
                cached = existing["response_payload"]
                return JSONResponse(
                    status_code=cached.get("_status_code", 200),
                    content=cached.get("body", cached),
                    headers={"X-Cache-Lookup": "HIT-IDEMPOTENT"},
                )

        # 2. Process request
        response = await call_next(request)

        # 3. Cache successful responses
        if 200 <= response.status_code < 500:
            resp_body_bytes = b""
            async for chunk in response.body_iterator:
                resp_body_bytes += chunk

            try:
                resp_json = json.loads(resp_body_bytes.decode("utf-8"))
            except Exception:
                resp_json = {"raw": resp_body_bytes.decode("utf-8", errors="replace")}

            payload_to_store = {"_status_code": response.status_code, "body": resp_json}

            try:
                async with pool.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO idempotency_keys (key, response_payload)
                        VALUES ($1, $2)
                        ON CONFLICT (key) DO NOTHING
                        """,
                        key, payload_to_store,
                    )
            except Exception as exc:
                logger.warning("Failed storing idempotency key %s: %s", key, exc)

            headers = dict(response.headers)
            headers["X-Cache-Lookup"] = "MISS-SAVED"
            return JSONResponse(
                status_code=response.status_code,
                content=resp_json,
                headers=headers,
            )

        return response
