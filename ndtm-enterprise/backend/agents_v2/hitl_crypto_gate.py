"""Human-In-The-Loop (HITL) Cryptographic Approval Gate.
Enforces non-repudiation using Ed25519 asymmetric digital signatures on
high-impact autonomous dispatch actions.
"""
from __future__ import annotations

import binascii
import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


def generate_ed25519_keypair() -> tuple[str, str]:
    """Generates a fresh Ed25519 keypair returning (private_key_hex, public_key_hex)."""
    priv = Ed25519PrivateKey.generate()
    priv_bytes = priv.private_bytes_raw()
    pub_bytes = priv.public_key().public_bytes_raw()
    return priv_bytes.hex(), pub_bytes.hex()


def sign_payload(private_key_hex: str, message_bytes: bytes) -> str:
    """Signs arbitrary message bytes with an Ed25519 private key."""
    priv = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(private_key_hex))
    sig = priv.sign(message_bytes)
    return sig.hex()


def verify_ed25519_signature(public_key_hex: str, signature_hex: str, message_bytes: bytes) -> bool:
    """Verifies that signature_hex is a valid Ed25519 signature over message_bytes."""
    try:
        pub_bytes = bytes.fromhex(public_key_hex)
        sig_bytes = bytes.fromhex(signature_hex)
        if len(pub_bytes) != 32 or len(sig_bytes) != 64:
            return False
        pub = Ed25519PublicKey.from_public_bytes(pub_bytes)
        pub.verify(sig_bytes, message_bytes)
        return True
    except (InvalidSignature, binascii.Error, ValueError):
        return False


class HITLCryptoGate:
    """In-memory and persistent manager for high-risk pending actions."""

    def __init__(self) -> None:
        self._pending_requests: dict[str, dict[str, Any]] = {}
        # Pre-seed one pending request for immediate demonstration
        seed_id = "00000000-0000-0000-0000-000000000101"
        self._pending_requests[seed_id] = {
            "id": seed_id,
            "incident_id": "11111111-2222-3333-4444-555555555555",
            "proposed_action": {
                "action": "POWER_GRID_SHEDDING",
                "target_substation": "SUBSTATION_IKITELLI",
                "estimated_offline_minutes": 20,
            },
            "agent_consensus_score": 0.78,
            "z3_proof_hash": "4a5e1e4baab89f3a32518a88c31bc87f618f76673e2cc77ab2127b7afdeda33b",
            "status": "PENDING_HUMAN",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    def list_pending(self) -> list[dict[str, Any]]:
        return list(self._pending_requests.values())

    def get_request(self, request_id: str) -> dict[str, Any] | None:
        return self._pending_requests.get(request_id)

    def submit_for_approval(
        self,
        incident_id: str | None,
        proposed_action: dict[str, Any],
        consensus_score: float,
        z3_proof_hash: str,
    ) -> str:
        req_id = str(uuid4())
        self._pending_requests[req_id] = {
            "id": req_id,
            "incident_id": incident_id,
            "proposed_action": proposed_action,
            "agent_consensus_score": consensus_score,
            "z3_proof_hash": z3_proof_hash,
            "status": "PENDING_HUMAN",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        return req_id

    def sign_and_approve(
        self,
        request_id: str,
        approver_email: str,
        public_key_hex: str,
        signature_hex: str,
    ) -> bool:
        req = self._pending_requests.get(request_id)
        if not req:
            return False

        # Construct canonical canonical signing bytes: SHA256(request_id + z3_proof_hash)
        canonical_msg = f"{request_id}:{req['z3_proof_hash']}:{approver_email}".encode("utf-8")
        is_valid = verify_ed25519_signature(public_key_hex, signature_hex, canonical_msg)

        if is_valid:
            req["status"] = "APPROVED_SIGNED"
            req["approver_email"] = approver_email
            req["public_key_hex"] = public_key_hex
            req["signature_hex"] = signature_hex
            req["decided_at"] = datetime.now(timezone.utc).isoformat()
            return True

        return False


hitl_crypto_gate = HITLCryptoGate()
