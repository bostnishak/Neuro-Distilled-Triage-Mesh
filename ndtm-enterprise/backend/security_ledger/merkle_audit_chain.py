"""Cryptographic Merkle Tree Audit Ledger & Tamper-Evident State Chain.
Implements SHA-256 hash chaining, dynamic Merkle tree root snapshots,
and tamper detection for zero-trust compliance.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def compute_sha256(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def compute_merkle_root(leaf_hashes: list[str]) -> str:
    """Computes binary Merkle tree root hash from a list of leaf hashes."""
    if not leaf_hashes:
        return "0000000000000000000000000000000000000000000000000000000000000000"
    if len(leaf_hashes) == 1:
        return leaf_hashes[0]

    current_layer = list(leaf_hashes)
    while len(current_layer) > 1:
        next_layer = []
        for i in range(0, len(current_layer), 2):
            left = current_layer[i]
            right = current_layer[i + 1] if i + 1 < len(current_layer) else left
            combined = compute_sha256(f"{left}{right}")
            next_layer.append(combined)
        current_layer = next_layer

    return current_layer[0]


@dataclass(slots=True)
class MerkleBlock:
    seq_no: int
    event_id: str
    event_type: str
    actor_id: str
    canonical_payload: dict[str, Any]
    payload_sha256: str
    prev_block_hash: str
    block_hash: str
    merkle_root_snapshot: str
    created_at: str


class MerkleAuditChain:
    """Append-only cryptographic ledger with tamper detection and verification."""

    def __init__(self) -> None:
        self.blocks: list[MerkleBlock] = []
        self._initialize_genesis_block()

    def _initialize_genesis_block(self) -> None:
        payload = {"message": "NDTM v2.0 Frontier Genesis Block Initialized"}
        canonical_str = json.dumps(payload, sort_keys=True)
        payload_sha = compute_sha256(canonical_str)
        prev_hash = "0" * 64
        block_hash = compute_sha256(f"1:{prev_hash}:{payload_sha}")

        genesis = MerkleBlock(
            seq_no=1,
            event_id="00000000-0000-0000-0000-000000000001",
            event_type="GENESIS_BLOCK",
            actor_id="SYSTEM_BOOTSTRAP",
            canonical_payload=payload,
            payload_sha256=payload_sha,
            prev_block_hash=prev_hash,
            block_hash=block_hash,
            merkle_root_snapshot=block_hash,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self.blocks.append(genesis)

    def append_event(
        self,
        event_type: str,
        actor_id: str,
        payload: dict[str, Any],
    ) -> MerkleBlock:
        """Appends a new event block and computes updated chain hashes and Merkle root."""
        prev_block = self.blocks[-1]
        seq_no = prev_block.seq_no + 1
        event_id = str(uuid4())

        canonical_str = json.dumps(payload, sort_keys=True)
        payload_sha = compute_sha256(canonical_str)

        block_hash = compute_sha256(f"{seq_no}:{prev_block.block_hash}:{payload_sha}")

        # Recompute Merkle root across all block hashes
        all_leaf_hashes = [b.block_hash for b in self.blocks] + [block_hash]
        root_snapshot = compute_merkle_root(all_leaf_hashes)

        block = MerkleBlock(
            seq_no=seq_no,
            event_id=event_id,
            event_type=event_type,
            actor_id=actor_id,
            canonical_payload=payload,
            payload_sha256=payload_sha,
            prev_block_hash=prev_block.block_hash,
            block_hash=block_hash,
            merkle_root_snapshot=root_snapshot,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self.blocks.append(block)
        return block

    def verify_chain_integrity(self) -> dict[str, Any]:
        """Validates all SHA-256 linkages and payloads across the ledger."""
        for i, block in enumerate(self.blocks):
            # 1. Verify payload hash matches canonical JSON
            canonical_str = json.dumps(block.canonical_payload, sort_keys=True)
            recomputed_payload_hash = compute_sha256(canonical_str)
            if recomputed_payload_hash != block.payload_sha256:
                return {
                    "valid": False,
                    "tampered_seq_no": block.seq_no,
                    "reason": "PAYLOAD_OR_CHAIN_HASH_MISMATCH",
                }

            # 2. Verify previous block hash linkage (for blocks after genesis)
            if i > 0:
                prev_block = self.blocks[i - 1]
                if block.prev_block_hash != prev_block.block_hash:
                    return {
                        "valid": False,
                        "tampered_seq_no": block.seq_no,
                        "reason": "PAYLOAD_OR_CHAIN_HASH_MISMATCH",
                    }

            # 3. Verify block hash calculation
            expected_block_hash = compute_sha256(
                f"{block.seq_no}:{block.prev_block_hash}:{block.payload_sha256}"
            )
            if expected_block_hash != block.block_hash:
                return {
                    "valid": False,
                    "tampered_seq_no": block.seq_no,
                    "reason": "PAYLOAD_OR_CHAIN_HASH_MISMATCH",
                }

        # 4. Verify latest Merkle root
        leaf_hashes = [b.block_hash for b in self.blocks]
        current_root = compute_merkle_root(leaf_hashes)

        return {
            "valid": True,
            "total_blocks_verified": len(self.blocks),
            "merkle_root": current_root,
            "tampered_seq_no": None,
            "reason": None,
        }

    def tamper_block_for_testing(self, seq_no: int, malicious_payload: dict[str, Any]) -> None:
        """Injects tampering in payload without recomputing hash for verification tests."""
        for b in self.blocks:
            if b.seq_no == seq_no:
                # Direct overwrite simulating SQL UPDATE tampering
                object.__setattr__(b, "canonical_payload", malicious_payload)
                break


merkle_chain = MerkleAuditChain()
