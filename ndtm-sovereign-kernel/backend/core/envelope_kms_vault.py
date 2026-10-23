"""
Neuro-Distilled Triage Mesh (NDTM) — Sovereign Distributed & Failure-Proof Kernel
RFC-NDTM-OMEGA: Production Hardening Engine v3.0

Phase 32: Envelope KMS Vault
Two-Tier AES-256-GCM Envelope Encryption (Master KEK + Per-Tenant DEKs)
Provides Zero-Trust Cryptographic Isolation with Master Key Rotation.
"""

from __future__ import annotations

import base64
import json
import os
import secrets
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


@dataclass
class EncryptedEnvelope:
    tenant_id: str
    kek_version: int
    wrapped_dek_b64: str    # Nonce (12B) + Encrypted DEK (32B) + Tag (16B) base64
    ciphertext_b64: str     # Nonce (12B) + Encrypted Data + Tag (16B) base64
    created_at: float

    def to_json(self) -> str:
        return json.dumps({
            "tenant_id": self.tenant_id,
            "kek_version": self.kek_version,
            "wrapped_dek_b64": self.wrapped_dek_b64,
            "ciphertext_b64": self.ciphertext_b64,
            "created_at": self.created_at,
        })

    @classmethod
    def from_json(cls, json_str: str) -> EncryptedEnvelope:
        d = json.loads(json_str)
        return cls(
            tenant_id=d["tenant_id"],
            kek_version=d["kek_version"],
            wrapped_dek_b64=d["wrapped_dek_b64"],
            ciphertext_b64=d["ciphertext_b64"],
            created_at=d["created_at"],
        )


class EnvelopeKMSVault:
    """
    Carrier-Grade Multi-Tenant Envelope Encryption Engine.
    
    1. Generates ephemeral 256-bit Data Encryption Keys (DEKs) per tenant or per transaction.
    2. Encrypts sensitive incident/telemetry payload using DEK with AES-256-GCM.
    3. Wraps (encrypts) DEK using root Master Key Encryption Key (KEK).
    4. Allows zero-downtime KEK rotation by re-wrapping DEKs without re-encrypting large datasets.
    """

    def __init__(self, master_keks: Optional[Dict[int, bytes]] = None):
        # kek_version -> 32-byte AESGCM key
        if master_keks:
            self.keks = {v: k for v, k in master_keks.items()}
            self.current_kek_version = max(self.keks.keys())
        else:
            # Generate initial root KEK v1
            self.current_kek_version = 1
            self.keks = {1: AESGCM.generate_key(bit_length=256)}

    def rotate_master_kek(self) -> int:
        """Generates a new KEK version and marks it as active for all future encryptions."""
        new_version = self.current_kek_version + 1
        new_key = AESGCM.generate_key(bit_length=256)
        self.keks[new_version] = new_key
        self.current_kek_version = new_version
        return new_version

    def encrypt(
        self,
        tenant_id: str,
        plaintext_data: bytes,
        associated_data: Optional[bytes] = None,
    ) -> EncryptedEnvelope:
        """
        Encrypts plaintext bytes using a freshly generated DEK,
        then wraps the DEK under the current active Master KEK.
        """
        # 1. Generate ephemeral DEK (32 bytes = 256 bits)
        dek = AESGCM.generate_key(bit_length=256)

        # 2. Encrypt plaintext with DEK using AES-256-GCM
        dek_aes = AESGCM(dek)
        data_nonce = secrets.token_bytes(12)  # Standard 96-bit GCM nonce
        ciphertext = dek_aes.encrypt(data_nonce, plaintext_data, associated_data)
        full_ciphertext = data_nonce + ciphertext  # Pack nonce + ciphertext_with_tag

        # 3. Wrap DEK with active Master KEK
        active_kek_bytes = self.keks[self.current_kek_version]
        kek_aes = AESGCM(active_kek_bytes)
        dek_nonce = secrets.token_bytes(12)
        # Wrap DEK with tenant_id bound as associated data to prevent cross-tenant DEK transplant attacks
        tenant_ad = tenant_id.encode("utf-8")
        wrapped_dek = kek_aes.encrypt(dek_nonce, dek, tenant_ad)
        full_wrapped_dek = dek_nonce + wrapped_dek

        return EncryptedEnvelope(
            tenant_id=tenant_id,
            kek_version=self.current_kek_version,
            wrapped_dek_b64=base64.b64encode(full_wrapped_dek).decode("ascii"),
            ciphertext_b64=base64.b64encode(full_ciphertext).decode("ascii"),
            created_at=time.time(),
        )

    def decrypt(
        self,
        envelope: EncryptedEnvelope,
        associated_data: Optional[bytes] = None,
    ) -> bytes:
        """
        Unwraps DEK using appropriate KEK version, then decrypts ciphertext payload.
        """
        kek_version = envelope.kek_version
        if kek_version not in self.keks:
            raise KeyError(f"KEK version {kek_version} not found in KMS vault keyring.")

        kek_bytes = self.keks[kek_version]
        kek_aes = AESGCM(kek_bytes)

        # 1. Unwrap DEK
        full_wrapped = base64.b64decode(envelope.wrapped_dek_b64.encode("ascii"))
        dek_nonce = full_wrapped[:12]
        wrapped_body = full_wrapped[12:]
        tenant_ad = envelope.tenant_id.encode("utf-8")

        dek = kek_aes.decrypt(dek_nonce, wrapped_body, tenant_ad)

        # 2. Decrypt Ciphertext with unwrapped DEK
        full_cipher = base64.b64decode(envelope.ciphertext_b64.encode("ascii"))
        data_nonce = full_cipher[:12]
        ciphertext_body = full_cipher[12:]

        dek_aes = AESGCM(dek)
        plaintext = dek_aes.decrypt(data_nonce, ciphertext_body, associated_data)
        return plaintext

    def rewrap_envelope(self, envelope: EncryptedEnvelope) -> EncryptedEnvelope:
        """
        Re-wraps envelope's DEK under the newest active Master KEK
        WITHOUT decrypting the underlying data payload.
        """
        if envelope.kek_version == self.current_kek_version:
            return envelope  # Already on latest KEK

        # Unwrap DEK with old KEK
        old_kek = self.keks[envelope.kek_version]
        kek_aes_old = AESGCM(old_kek)
        full_wrapped = base64.b64decode(envelope.wrapped_dek_b64.encode("ascii"))
        dek_nonce = full_wrapped[:12]
        wrapped_body = full_wrapped[12:]
        tenant_ad = envelope.tenant_id.encode("utf-8")
        dek = kek_aes_old.decrypt(dek_nonce, wrapped_body, tenant_ad)

        # Wrap DEK with newest active KEK
        new_kek = self.keks[self.current_kek_version]
        kek_aes_new = AESGCM(new_kek)
        new_dek_nonce = secrets.token_bytes(12)
        new_wrapped_dek = kek_aes_new.encrypt(new_dek_nonce, dek, tenant_ad)
        new_full_wrapped = new_dek_nonce + new_wrapped_dek

        return EncryptedEnvelope(
            tenant_id=envelope.tenant_id,
            kek_version=self.current_kek_version,
            wrapped_dek_b64=base64.b64encode(new_full_wrapped).decode("ascii"),
            ciphertext_b64=envelope.ciphertext_b64,  # Bulk ciphertext untouched
            created_at=envelope.created_at,
        )
