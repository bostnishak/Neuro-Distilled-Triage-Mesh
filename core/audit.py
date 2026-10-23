"""Append-only audit trail helper."""
from __future__ import annotations

from typing import Any

import asyncpg

from core.logging_config import request_id_ctx


async def write_audit(
    conn: asyncpg.Connection,
    *,
    entity_type: str,
    entity_id: Any,
    action: str,
    actor: str = "system",
    details: dict[str, Any] | None = None,
) -> None:
    """Insert an audit record inside the caller's transaction."""
    await conn.execute(
        """
        INSERT INTO audit_logs (entity_type, entity_id, action, actor, details, request_id)
        VALUES ($1, $2, $3, $4, $5, $6)
        """,
        entity_type,
        str(entity_id) if entity_id is not None else None,
        action,
        actor,
        details or {},
        request_id_ctx.get(),
    )
