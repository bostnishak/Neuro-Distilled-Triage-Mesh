"""Authentication REST router: Login, registration, token refresh, and logout."""
from __future__ import annotations

import logging
from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user, get_db, get_redis
from backend.core.security import (
    create_access_token,
    create_refresh_token,
    decode_jwt_token,
    get_password_hash,
    verify_password,
)
from backend.db.models import User
from backend.db.repositories import UserRepository
from backend.schemas.auth import (
    TokenResponse,
    UserLoginRequest,
    UserProfileResponse,
    UserRegisterRequest,
    UserRole,
)

logger = logging.getLogger("api.auth")
router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=UserProfileResponse, status_code=status.HTTP_201_CREATED)
async def register_user(
    req: UserRegisterRequest,
    session: AsyncSession = Depends(get_db),
) -> UserProfileResponse:
    """Registers a new user account with Argon2id password hash."""
    existing = await UserRepository.get_by_email(session, req.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email address already exists.",
        )

    pwd_hash = get_password_hash(req.password)
    user = await UserRepository.create(session, req.email, pwd_hash, req.role)
    await session.commit()
    logger.info("New user registered: %s (Role: %s)", user.email, user.role)

    return UserProfileResponse(
        id=user.id,
        email=user.email,
        role=UserRole(user.role),
        is_active=user.is_active,
        created_at=user.created_at,
    )


@router.post("/login", response_model=TokenResponse)
async def login_user(
    req: UserLoginRequest,
    session: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Authenticates credentials and returns JWT Access and Refresh tokens."""
    user = await UserRepository.get_by_email(session, req.email)
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated.",
        )

    access_tok = create_access_token(str(user.id), user.role)
    refresh_tok = create_refresh_token(str(user.id), user.role)

    logger.info("User login successful: %s", user.email)
    return TokenResponse(
        access_token=access_tok,
        refresh_token=refresh_tok,
        user_id=user.id,
        email=user.email,
        role=UserRole(user.role),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_access_token(
    refresh_token: str,
    session: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Issues a new access token using a valid refresh token."""
    try:
        payload = decode_jwt_token(refresh_token)
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type.")
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(err))

    import uuid
    user = await UserRepository.get_by_id(session, uuid.UUID(payload["sub"]))
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User invalid.")

    new_access = create_access_token(str(user.id), user.role)
    new_refresh = create_refresh_token(str(user.id), user.role)

    return TokenResponse(
        access_token=new_access,
        refresh_token=new_refresh,
        user_id=user.id,
        email=user.email,
        role=UserRole(user.role),
    )


@router.get("/me", response_model=UserProfileResponse)
async def get_my_profile(
    current_user: User = Depends(get_current_user),
) -> UserProfileResponse:
    """Returns profile for currently authenticated user."""
    return UserProfileResponse(
        id=current_user.id,
        email=current_user.email,
        role=UserRole(current_user.role),
        is_active=current_user.is_active,
        created_at=current_user.created_at,
    )
