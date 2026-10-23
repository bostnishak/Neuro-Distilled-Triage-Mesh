"""Asynchronous PostgreSQL session management via SQLAlchemy 2.0 and direct asyncpg pool."""
from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import asyncpg
from pgvector.asyncpg import register_vector
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base

from backend.core.config import get_settings

logger = logging.getLogger("db.session")
settings = get_settings()

Base = declarative_base()

# SQLAlchemy Async Engine
engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=15,
    max_overflow=25,
    pool_recycle=300,
    pool_pre_ping=True,
    echo=settings.DEBUG,
)

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

_asyncpg_pool: asyncpg.Pool | None = None


async def _init_asyncpg_codecs(conn: asyncpg.Connection) -> None:
    """Setup pgvector codec and JSONB encoder/decoders."""
    await register_vector(conn)
    await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")
    await conn.set_type_codec("json", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")


async def init_asyncpg_pool() -> asyncpg.Pool:
    """Initializes raw asyncpg connection pool for ultra-low latency spatial and vector operations."""
    global _asyncpg_pool
    if _asyncpg_pool is None:
        raw_dsn = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
        _asyncpg_pool = await asyncpg.create_pool(
            dsn=raw_dsn,
            min_size=4,
            max_size=20,
            command_timeout=20.0,
            init=_init_asyncpg_codecs,
            server_settings={"application_name": "NDTM_Enterprise_Core", "hnsw.ef_search": "100"},
        )
        logger.info("Raw asyncpg connection pool initialized.")
    return _asyncpg_pool


async def close_database_connections() -> None:
    """Closes SQLAlchemy engine and raw asyncpg pool."""
    global _asyncpg_pool
    if _asyncpg_pool:
        await _asyncpg_pool.close()
        _asyncpg_pool = None
    await engine.dispose()
    logger.info("Database connections disposed gracefully.")


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency yielding a transactional SQLAlchemy AsyncSession."""
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_raw_connection() -> AsyncGenerator[asyncpg.Connection, None]:
    """Context manager yielding a pooled raw asyncpg connection."""
    pool = await init_asyncpg_pool()
    async with pool.acquire() as conn:
        yield conn
