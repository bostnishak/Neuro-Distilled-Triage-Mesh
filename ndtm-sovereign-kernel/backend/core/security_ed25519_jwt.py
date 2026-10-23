import datetime
import hashlib
import hmac
import os
from typing import Any, Dict, Optional, Tuple

import jwt
from cryptography.hazmat.primitives.asymmetric import ed25519

from core.config import settings

# PyJWT and cryptography are hard requirements. There is intentionally no
# degraded mode: a missing crypto library must stop the process rather than
# silently downgrade signatures to something forgeable.

try:
    from argon2 import PasswordHasher

    _HAS_ARGON2 = True
    _pwd_hasher = PasswordHasher(
        time_cost=3,
        memory_cost=65536,
        parallelism=4,
        hash_len=32,
        salt_len=16,
    )
except ImportError:
    _HAS_ARGON2 = False


def hash_password(password: str) -> str:
    """Hashes a raw password string using Argon2id with scrypt fallback."""
    if _HAS_ARGON2:
        return _pwd_hasher.hash(password)
    salt = os.urandom(16)
    key = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=16384, r=8, p=1, maxmem=0, dklen=32)
    return f"$scrypt$n=16384,r=8,p=1${salt.hex()}${key.hex()}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain password against an Argon2id or scrypt hash."""
    if _HAS_ARGON2 and hashed_password.startswith("$argon2"):
        try:
            return _pwd_hasher.verify(hashed_password, plain_password)
        except Exception:
            return False
    elif hashed_password.startswith("$scrypt$"):
        try:
            parts = hashed_password.split("$")
            salt = bytes.fromhex(parts[3])
            expected_key = parts[4]
            key = hashlib.scrypt(plain_password.encode("utf-8"), salt=salt, n=16384, r=8, p=1, maxmem=0, dklen=32)
            return hmac.compare_digest(key.hex(), expected_key)
        except Exception:
            return False
    return False


def create_access_token(
    subject: str,
    role: str,
    permissions: list[str],
    expires_delta: Optional[datetime.timedelta] = None,
) -> str:
    """Creates a signed RFC 7519 JWT access token."""
    now = datetime.datetime.now(datetime.timezone.utc)
    if expires_delta is not None:
        expire = now + expires_delta
    else:
        expire = now + datetime.timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    payload: Dict[str, Any] = {
        "sub": subject,
        "role": role,
        "perms": permissions,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "iss": "ndtm-sovereign-kernel",
        "jti": os.urandom(16).hex(),
    }
    return jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> Dict[str, Any]:
    """Decodes and validates a JWT token. Raises on any validation failure."""
    return jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
        issuer="ndtm-sovereign-kernel",
        options={"require": ["exp", "iat", "sub", "iss"]},
    )


class Ed25519Signer:
    """Real Ed25519 signing and verification. No HMAC substitute exists."""

    def __init__(self, private_key_hex: Optional[str] = None, public_key_hex: Optional[str] = None):
        self._private_key: Optional[ed25519.Ed25519PrivateKey] = None
        self._public_key: ed25519.Ed25519PublicKey

        priv_hex = private_key_hex or settings.ED25519_PRIVATE_KEY_HEX
        pub_hex = public_key_hex or settings.ED25519_PUBLIC_KEY_HEX

        if priv_hex:
            self._private_key = ed25519.Ed25519PrivateKey.from_private_bytes(bytes.fromhex(priv_hex))
            self._public_key = self._private_key.public_key()
        elif pub_hex:
            self._public_key = ed25519.Ed25519PublicKey.from_public_bytes(bytes.fromhex(pub_hex))
        else:
            # Ephemeral key: valid for this process only, never persisted.
            self._private_key = ed25519.Ed25519PrivateKey.generate()
            self._public_key = self._private_key.public_key()

    @property
    def public_key_hex(self) -> str:
        return self._public_key.public_bytes_raw().hex()

    def sign_bytes(self, data: bytes) -> bytes:
        if self._private_key is None:
            raise PermissionError("This signer holds only a public key and cannot sign.")
        return self._private_key.sign(data)

    def sign_hex(self, data: bytes) -> str:
        return self.sign_bytes(data).hex()

    def verify(self, signature_bytes: bytes, data: bytes) -> bool:
        try:
            self._public_key.verify(signature_bytes, data)
            return True
        except Exception:
            return False

    def verify_hex(self, signature_hex: str, data: bytes) -> bool:
        try:
            return self.verify(bytes.fromhex(signature_hex), data)
        except Exception:
            return False

    @classmethod
    def verify_with_public_key(cls, pub_hex: str, signature_hex: str, data: bytes) -> bool:
        try:
            key = ed25519.Ed25519PublicKey.from_public_bytes(bytes.fromhex(pub_hex))
            key.verify(bytes.fromhex(signature_hex), data)
            return True
        except Exception:
            return False

    @classmethod
    def generate_keypair(cls) -> Tuple[str, str]:
        priv = ed25519.Ed25519PrivateKey.generate()
        return priv.private_bytes_raw().hex(), priv.public_key().public_bytes_raw().hex()


global_signer = Ed25519Signer()
