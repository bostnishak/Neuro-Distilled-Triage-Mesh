"""FastAPI dependency injection: Database sessions, Redis clients, JWT RBAC, and current user."""
from __future__ import annotations

import logging
from typing import AsyncGenerator, Callable

import redis.asyncio as aioredis
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import get_settings
from backend.core.exceptions import AuthenticationError, AuthorizationError
from backend.core.security import decode_jwt_token
from backend.db.models import User
from backend.db.repositories import UserRepository
from backend.db.session import async_session_factory
from backend.schemas.auth import UserRole

logger = logging.getLogger("api.deps")
settings = get_settings()
security_bearer = HTTPBearer(auto_error=False)

_redis_pool: aioredis.Redis | None = None


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Provides a transactional database session."""
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_redis() -> aioredis.Redis | None:
    """Provides singleton Redis connection with graceful fallback."""
    global _redis_pool
    if _redis_pool is None:
        try:
            _redis_pool = aioredis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                max_connections=20,
            )
            await _redis_pool.ping()
        except Exception as exc:
            logger.warning("Redis connection failed in dependency: %s", exc)
            return None
    return _redis_pool


async def get_current_user(
    auth: HTTPAuthorizationCredentials | None = Depends(security_bearer),
    session: AsyncSession = Depends(get_db),
    redis_client: aioredis.Redis | None = Depends(get_redis),
) -> User:
    """Decodes JWT, verifies JTI revocation list in Redis, and retrieves active User record."""
    if not auth:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header with Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_jwt_token(auth.credentials)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(err),
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check JTI Revocation in Redis
    jti = payload.get("jti")
    if redis_client and jti:
        try:
            is_revoked = await redis_client.get(f"revoked_jti:{jti}")
            if is_revoked:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token has been revoked.",
                    headers={"WWW-Authenticate": "Bearer"},
                )
        except HTTPException:
            raise
        except Exception as exc:
            logger.debug("JTI revocation check skipped on redis error: %s", exc)

    import uuid
    user_id_str = payload.get("sub")
    if not user_id_str:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token subject.")

    user = await UserRepository.get_by_id(session, uuid.UUID(user_id_str))
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or deactivated.")

    return user


def require_role(allowed_roles: list[UserRole | str]) -> Callable:
    """RBAC Guard dependency enforcing strict role boundaries."""
    role_strings = [r.value if isinstance(r, UserRole) else str(r) for r in allowed_roles]

    async def _role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in role_strings:
            logger.warning(
                "Access denied for user %s (%s). Required roles: %s",
                current_user.email,
                current_user.role,
                role_strings,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation requires one of the following roles: {role_strings}",
            )
        return current_user

    return _role_checker
