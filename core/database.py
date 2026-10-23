"""asyncpg connection pool with pgvector + JSONB codecs."""
from __future__ import annotations

import asyncio
import json
import logging

import asyncpg
from pgvector.asyncpg import register_vector

from core.config import Settings

logger = logging.getLogger(__name__)


async def _init_connection(conn: asyncpg.Connection) -> None:
    """Per-connection setup: vector type codec and transparent JSONB (de)serialisation."""
    await register_vector(conn)
    await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")
    await conn.set_type_codec("json", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")


async def create_pool(settings: Settings, attempts: int = 20) -> asyncpg.Pool:
    """Create the pool, retrying with exponential backoff while the DB boots."""
    server_settings = {
        "application_name": settings.app_name[:60],
        # Sent at connection start-up so it survives asyncpg's RESET ALL on release.
        "hnsw.ef_search": str(settings.hnsw_ef_search),
        # pgvector >= 0.8: keep scanning the HNSW graph when WHERE filters drop rows.
        "hnsw.iterative_scan": "relaxed_order",
    }
    for attempt in range(1, attempts + 1):
        try:
            pool = await asyncpg.create_pool(
                dsn=settings.database_url,
                min_size=settings.db_pool_min_size,
                max_size=settings.db_pool_max_size,
                command_timeout=settings.db_command_timeout_seconds,
                init=_init_connection,
                server_settings=server_settings,
            )
            assert pool is not None
            logger.info("PostgreSQL pool ready", extra={"min": settings.db_pool_min_size,
                                                         "max": settings.db_pool_max_size})
            return pool
        except (OSError, asyncpg.PostgresError, asyncpg.InterfaceError) as exc:
            if attempt == attempts:
                logger.error("Giving up connecting to PostgreSQL", exc_info=True)
                raise
            delay = min(2 ** (attempt - 1) * 0.5, 10.0)
            logger.warning("PostgreSQL not ready (%s); retry %d/%d in %.1fs", exc, attempt, attempts, delay)
            await asyncio.sleep(delay)
    raise RuntimeError("unreachable")
