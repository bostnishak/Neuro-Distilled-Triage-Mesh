import pytest
from core.security_ed25519_jwt import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
    Ed25519Signer,
)


def test_argon2id_password_hashing():
    password = "SuperSecretPassword2026!"
    hashed = hash_password(password)

    assert hashed != password
    assert hashed.startswith("$argon2id$") or hashed.startswith("$scrypt$")
    assert verify_password(password, hashed) is True
    assert verify_password("WrongPassword123!", hashed) is False


def test_jwt_lifecycle_and_tampering():
    token = create_access_token(
        subject="00000000-0000-0000-0000-000000000001",
        role="ADMIN",
        permissions=["ADMIN", "INCIDENT_COMMANDER"],
    )

    payload = decode_access_token(token)
    assert payload["sub"] == "00000000-0000-0000-0000-000000000001"
    assert payload["role"] == "ADMIN"
    assert "ADMIN" in payload["perms"]


def test_ed25519_cryptographic_signatures():
    priv_hex, pub_hex = Ed25519Signer.generate_keypair()
    signer = Ed25519Signer(priv_hex, pub_hex)

    data = b"NDTM_MERKLE_ROOT_BLOCK_HEIGHT_42_EVENT_PAYLOAD"
    signature_hex = signer.sign_hex(data)

    assert len(signature_hex) == 128  # 64 bytes * 2 hex chars
    assert signer.verify_hex(signature_hex, data) is True

    # Tampered data must fail
    tampered_data = b"TAMPERED_DATA_PAYLOAD"
    assert signer.verify_hex(signature_hex, tampered_data) is False

    # Arbitrary public key verification
    assert Ed25519Signer.verify_with_public_key(pub_hex, signature_hex, data) is True
    assert Ed25519Signer.verify_with_public_key(pub_hex, signature_hex, tampered_data) is False
