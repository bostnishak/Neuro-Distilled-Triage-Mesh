from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from core.security_ed25519_jwt import verify_password, create_access_token
from infrastructure.database.connection import get_db
from infrastructure.database.orm_models import UserOrm
from presentation.api.dependencies import get_current_user

router = APIRouter(prefix="/auth", tags=["Authentication & RBAC"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: Dict[str, Any]


@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest, session: AsyncSession = Depends(get_db)) -> LoginResponse:
    """Authenticates operator via Argon2id password hash and issues RFC 7519 JWT."""
    stmt = select(UserOrm).where(UserOrm.email == req.email)
    res = await session.execute(stmt)
    user = res.scalar_one_or_none()

    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled.",
        )

    token = create_access_token(
        subject=str(user.id),
        role=user.role,
        permissions=[user.role],
    )

    return LoginResponse(
        access_token=token,
        user={
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
        },
    )


@router.get("/me")
async def get_me(current_user: UserOrm = Depends(get_current_user)) -> Dict[str, Any]:
    """Returns currently authenticated operator profile."""
    return {
        "id": str(current_user.id),
        "email": current_user.email,
        "full_name": current_user.full_name,
        "role": current_user.role,
        "is_active": current_user.is_active,
        "created_at": current_user.created_at.isoformat(),
    }
