import uuid
from typing import AsyncGenerator, Callable
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from core.security_ed25519_jwt import decode_access_token
from core.exceptions import AuthenticationError, AuthorizationError
from infrastructure.database.connection import get_db
from infrastructure.database.orm_models import UserOrm


async def get_current_user(
    authorization: str = Header(..., description="Bearer <JWT>"),
    session: AsyncSession = Depends(get_db),
) -> UserOrm:
    """Extracts and validates operator identity from Bearer JWT header."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format. Expected 'Bearer <token>'.",
        )
    token = authorization.split(" ", 1)[1]
    try:
        payload = decode_access_token(token)
        user_id_str = payload.get("sub")
        if not user_id_str:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token missing subject claim.")
        user_id = uuid.UUID(user_id_str)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Token verification failed: {str(e)}")

    user = await session.get(UserOrm, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User account is inactive or revoked.")

    return user


def require_role(allowed_role: str) -> Callable[[UserOrm], UserOrm]:
    """Dependency factory enforcing Role-Based Access Control (RBAC)."""
    async def role_checker(current_user: UserOrm = Depends(get_current_user)) -> UserOrm:
        if current_user.role not in ("ADMIN", "ARCHITECT") and current_user.role != allowed_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation requires '{allowed_role}' or 'ARCHITECT' role. You have '{current_user.role}'.",
            )
        return current_user
    return role_checker
