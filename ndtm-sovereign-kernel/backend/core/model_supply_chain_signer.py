"""
Neuro-Distilled Triage Mesh (NDTM) — Sovereign Distributed & Failure-Proof Kernel
RFC-NDTM-OMEGA: Production Hardening Engine v3.0

Phase 32: Model Supply Chain Signer
Ed25519 Cryptographic Signature Verification for ONNX & LoRA Model Weights.
Prevents Model Tampering, Poisoned Artifacts, and Supply Chain Injections.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import ed25519


class ModelTamperedSecurityException(Exception):
    """Raised when model weights fail SHA-256 integrity or Ed25519 signature checks."""
    pass


@dataclass
class ModelSignatureManifest:
    model_name: str
    version: str
    sha256_hash: str
    file_size_bytes: int
    signed_at: float
    public_key_hex: str
    signature_hex: str

    def to_json(self) -> str:
        return json.dumps(
            {
                "model_name": self.model_name,
                "version": self.version,
                "sha256_hash": self.sha256_hash,
                "file_size_bytes": self.file_size_bytes,
                "signed_at": self.signed_at,
                "public_key_hex": self.public_key_hex,
                "signature_hex": self.signature_hex,
            },
            indent=2,
        )

    @classmethod
    def from_json(cls, json_str: str) -> ModelSignatureManifest:
        data = json.loads(json_str)
        return cls(
            model_name=data["model_name"],
            version=data["version"],
            sha256_hash=data["sha256_hash"],
            file_size_bytes=data["file_size_bytes"],
            signed_at=data["signed_at"],
            public_key_hex=data["public_key_hex"],
            signature_hex=data["signature_hex"],
        )


class ModelSupplyChainSigner:
    """
    Carrier-Grade Model Verification Engine.
    Enforces that zero ONNX/LoRA models are loaded into RAM or GPU without
    passing Ed25519 signature validation against trusted root public keys.
    """

    def __init__(self, trusted_public_keys_hex: Optional[List[str]] = None):
        self.trusted_keys: Set[str] = set(trusted_public_keys_hex or [])

    def add_trusted_key(self, public_key_hex: str) -> None:
        self.trusted_keys.add(public_key_hex.strip().lower())

    @staticmethod
    def generate_keypair() -> Tuple[ed25519.Ed25519PrivateKey, str, str]:
        """Generates a fresh Ed25519 keypair, returning (private_key, priv_hex, pub_hex)."""
        priv = ed25519.Ed25519PrivateKey.generate()
        pub = priv.public_key()
        priv_bytes = priv.private_bytes_raw()
        pub_bytes = pub.public_bytes_raw()
        return priv, priv_bytes.hex(), pub_bytes.hex()

    @staticmethod
    def compute_sha256(file_path: Path) -> Tuple[str, int]:
        """Computes SHA-256 digest of binary artifact in streaming 64KB chunks."""
        hasher = hashlib.sha256()
        total_bytes = 0
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
                total_bytes += len(chunk)
        return hasher.hexdigest(), total_bytes

    def sign_model_artifact(
        self,
        artifact_path: Path,
        private_key: ed25519.Ed25519PrivateKey,
        model_name: str,
        version: str,
        output_manifest_path: Optional[Path] = None,
    ) -> ModelSignatureManifest:
        """Signs a model artifact and exports sidecar manifest."""
        path = Path(artifact_path)
        if not path.is_file():
            raise FileNotFoundError(f"Model artifact not found: {path}")

        sha256_hash, file_size = self.compute_sha256(path)
        pub_bytes = private_key.public_key().public_bytes_raw()
        pub_hex = pub_bytes.hex()

        # Sign canonical payload: f"{model_name}:{version}:{sha256_hash}:{file_size}"
        canonical_msg = f"{model_name}:{version}:{sha256_hash}:{file_size}".encode("utf-8")
        signature = private_key.sign(canonical_msg)
        sig_hex = signature.hex()

        manifest = ModelSignatureManifest(
            model_name=model_name,
            version=version,
            sha256_hash=sha256_hash,
            file_size_bytes=file_size,
            signed_at=time.time(),
            public_key_hex=pub_hex,
            signature_hex=sig_hex,
        )

        if output_manifest_path:
            with open(output_manifest_path, "w", encoding="utf-8") as f:
                f.write(manifest.to_json())

        return manifest

    def verify_model_artifact(
        self,
        artifact_path: Path,
        manifest_path: Path,
    ) -> bool:
        """
        Validates artifact integrity and cryptographic signature.
        Throws ModelTamperedSecurityException if verification fails.
        """
        art_path = Path(artifact_path)
        man_path = Path(manifest_path)

        if not art_path.is_file():
            raise ModelTamperedSecurityException(f"Missing model artifact: {art_path}")
        if not man_path.is_file():
            raise ModelTamperedSecurityException(f"Missing signature manifest: {man_path}")

        with open(man_path, "r", encoding="utf-8") as f:
            manifest = ModelSignatureManifest.from_json(f.read())

        # 1. Verify that the public key is trusted (Fail-closed)
        pub_hex = manifest.public_key_hex.lower()
        if not self.trusted_keys or pub_hex not in self.trusted_keys:
            raise ModelTamperedSecurityException(
                f"Untrusted signing key: {pub_hex}. Not in trusted root set or trust set is empty."
            )

        # 2. Verify SHA-256 hash
        actual_hash, actual_size = self.compute_sha256(art_path)
        if actual_hash != manifest.sha256_hash or actual_size != manifest.file_size_bytes:
            raise ModelTamperedSecurityException(
                f"Binary integrity mismatch! Actual SHA-256: {actual_hash}, Manifest SHA-256: {manifest.sha256_hash}"
            )

        # 3. Verify Ed25519 signature
        pub_key = ed25519.Ed25519PublicKey.from_public_bytes(bytes.fromhex(manifest.public_key_hex))
        canonical_msg = f"{manifest.model_name}:{manifest.version}:{manifest.sha256_hash}:{manifest.file_size_bytes}".encode("utf-8")
        sig_bytes = bytes.fromhex(manifest.signature_hex)

        try:
            pub_key.verify(sig_bytes, canonical_msg)
        except InvalidSignature:
            raise ModelTamperedSecurityException(
                f"Cryptographic signature check FAILED for {manifest.model_name} v{manifest.version}!"
            )

        return True
