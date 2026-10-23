"""PostgreSQL asyncpg connection pool with pgvector and JSONB codecs."""
from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import asyncpg
from pgvector.asyncpg import register_vector

logger = logging.getLogger("database")

_pool: asyncpg.Pool | None = None


async def _init_connection(conn: asyncpg.Connection) -> None:
    """Setup pgvector codec and transparent JSON codecs on every new connection."""
    await register_vector(conn)
    await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")
    await conn.set_type_codec("json", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")


async def init_db_pool(
    database_url: str | None = None,
    min_size: int = 2,
    max_size: int = 10,
    retries: int = 20,
) -> asyncpg.Pool:
    """Initialize the global asyncpg connection pool with exponential backoff."""
    global _pool
    dsn = database_url or os.getenv("DATABASE_URL", "postgresql://triage:triage_secret@localhost:5432/triage")
    
    server_settings = {
        "application_name": "NDTM_Platform",
        "hnsw.ef_search": "100",
    }

    for attempt in range(1, retries + 1):
        try:
            _pool = await asyncpg.create_pool(
                dsn=dsn,
                min_size=min_size,
                max_size=max_size,
                command_timeout=30.0,
                init=_init_connection,
                server_settings=server_settings,
            )
            logger.info("Database pool established successfully.")
            return _pool
        except Exception as exc:
            if attempt == retries:
                logger.error("Failed connecting to PostgreSQL after %d attempts: %s", retries, exc)
                raise
            delay = min(2 ** (attempt - 1) * 0.5, 10.0)
            logger.warning("PostgreSQL not ready (%s). Retrying %d/%d in %.1fs...", exc, attempt, retries, delay)
            await asyncio.sleep(delay)

    raise RuntimeError("Could not establish PostgreSQL connection pool.")


async def close_db_pool() -> None:
    """Gracefully terminate connection pool."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        logger.info("Database pool closed.")


def get_db_pool() -> asyncpg.Pool:
    """Return active pool instance."""
    if _pool is None:
        raise RuntimeError("Database pool has not been initialized.")
    return _pool


@asynccontextmanager
async def get_connection() -> AsyncGenerator[asyncpg.Connection, None]:
    """Context manager yielding a pooled connection."""
    pool = get_db_pool()
    async with pool.acquire() as conn:
        yield conn
