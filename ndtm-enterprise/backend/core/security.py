"""Security utilities: Argon2id password hashing, RS256/HS256 JWT RBAC, and HMAC pseudonymization."""
from __future__ import annotations

import hashlib
import hmac
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Sequence
from uuid import uuid4

try:
    import jwt
    ExpiredSignatureError = jwt.ExpiredSignatureError
    InvalidTokenError = getattr(jwt, "InvalidTokenError", getattr(jwt, "PyJWTError", Exception))
except ImportError:
    from jose import jwt
    from jose.exceptions import ExpiredSignatureError, JWTError as InvalidTokenError
from passlib.context import CryptContext

from backend.core.config import get_settings

settings = get_settings()

# Cryptographic password context (Argon2id preferred, bcrypt fallback)
pwd_context = CryptContext(
    schemes=["argon2", "bcrypt"],
    deprecated="auto",
    argon2__memory_cost=65536,
    argon2__time_cost=3,
    argon2__parallelism=4,
)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain password against an Argon2id/bcrypt hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Generates an Argon2id secure cryptographic password hash."""
    return pwd_context.hash(password)


def hmac_pseudonymize(data: str, salt: str | None = None) -> str:
    """Creates a deterministic HMAC-SHA256 pseudonym token for PII correlation without storing raw PII."""
    secret_salt = (salt or settings.HMAC_SECRET_SALT).encode("utf-8")
    mac = hmac.new(secret_salt, data.encode("utf-8"), hashlib.sha256).hexdigest()
    return mac[:8].upper()


def create_access_token(
    subject: str,
    role: str,
    expires_delta: timedelta | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Creates an asymmetric or cryptographic HMAC signed JWT access token."""
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "jti": str(uuid4()),
        "iat": int(time.time()),
        "exp": expire,
        "type": "access",
    }
    if extra_claims:
        to_encode.update(extra_claims)

    encoded_jwt = jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    return encoded_jwt


def create_refresh_token(subject: str, role: str) -> str:
    """Creates a long-lived refresh token (7 days default)."""
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode = {
        "sub": subject,
        "role": role,
        "jti": str(uuid4()),
        "iat": int(time.time()),
        "exp": expire,
        "type": "refresh",
    }
    return jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_jwt_token(token: str) -> dict[str, Any]:
    """Decodes and cryptographically validates a JWT token signature and expiration."""
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload
    except ExpiredSignatureError:
        raise ValueError("Token signature has expired.")
    except InvalidTokenError as exc:
        raise ValueError(f"Invalid token format: {exc}")
