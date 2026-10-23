"""Authentication, user profiles, and JWT token schemas."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class UserRole(str, Enum):
    OPERATOR = "OPERATOR"
    ARCHITECT = "ARCHITECT"
    AUDITOR = "AUDITOR"


class UserRegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    role: UserRole = UserRole.OPERATOR


class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in_seconds: int = 900
    user_id: UUID
    email: str
    role: UserRole


class UserProfileResponse(BaseModel):
    id: UUID
    email: str
    role: UserRole
    is_active: bool
    created_at: datetime
