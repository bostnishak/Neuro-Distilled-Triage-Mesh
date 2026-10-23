import datetime
import hashlib
from typing import List, Optional, Tuple
from core.exceptions import MerkleTamperDetectedException
from core.logging_otel import logger
from core.security_ed25519_jwt import global_signer
from domain.events import DomainEvent
from domain.value_objects import MerkleHash


class MerkleAuditLedger:
    """Cryptographic Merkle Audit Tree and Block Sealing Engine."""

    @staticmethod
    def build_merkle_root(leaf_hashes: List[MerkleHash]) -> MerkleHash:
        """Constructs balanced binary Merkle tree and returns top root hash."""
        if not leaf_hashes:
            return MerkleHash.compute(b"EMPTY_BLOCK_MERKLE_ROOT")

        current_level = list(leaf_hashes)

        while len(current_level) > 1:
            next_level: List[MerkleHash] = []
            for i in range(0, len(current_level), 2):
                left = current_level[i]
                # If odd number of leaves, duplicate the last element (standard RFC 6962)
                right = current_level[i + 1] if i + 1 < len(current_level) else left
                combined = MerkleHash.combine(left, right)
                next_level.append(combined)
            current_level = next_level

        return current_level[0]

    @classmethod
    def compute_block_hash(
        cls,
        parent_hash: str,
        merkle_root: str,
        height: int,
        timestamp_iso: str,
        events_count: int,
    ) -> MerkleHash:
        """Computes deterministic block hash: SHA256(parent || root || height || ts || count)."""
        preimage = f"{parent_hash}:{merkle_root}:{height}:{timestamp_iso}:{events_count}".encode("utf-8")
        return MerkleHash.compute(preimage)

    @classmethod
    def seal_block(
        cls,
        height: int,
        parent_hash: str,
        events: List[DomainEvent],
    ) -> Tuple[MerkleHash, MerkleHash, str, datetime.datetime]:
        """Batches domain events, computes Merkle root, computes block hash, and signs with Ed25519.

        Returns (block_hash, merkle_root, signature_hex, sealed_at).
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        leaf_hashes = [event.compute_hash() for event in events]
        merkle_root = cls.build_merkle_root(leaf_hashes)

        block_hash = cls.compute_block_hash(
            parent_hash=parent_hash,
            merkle_root=merkle_root.digest,
            height=height,
            timestamp_iso=now.isoformat(),
            events_count=len(events),
        )

        signature_hex = global_signer.sign_hex(bytes.fromhex(block_hash.digest))

        logger.info(
            "merkle_block_sealed",
            height=height,
            block_hash=block_hash.digest[:16],
            events_count=len(events),
        )
        return block_hash, merkle_root, signature_hex, now

    @classmethod
    def verify_chain_link(
        cls,
        prev_block_hash: str,
        current_parent_hash: str,
        current_block_hash: str,
        merkle_root: str,
        height: int,
        timestamp_iso: str,
        events_count: int,
        signature_hex: str,
    ) -> bool:
        """Verifies parent hash pointer, block SHA-256 calculation, and Ed25519 signature."""
        # 1. Parent pointer check
        if current_parent_hash != prev_block_hash:
            raise MerkleTamperDetectedException(height, prev_block_hash, current_parent_hash)

        # 2. Hash recalculation
        expected_hash = cls.compute_block_hash(
            current_parent_hash, merkle_root, height, timestamp_iso, events_count
        )
        if expected_hash.digest != current_block_hash:
            raise MerkleTamperDetectedException(height, expected_hash.digest, current_block_hash)

        # 3. Signature verification
        is_sig_valid = global_signer.verify_hex(signature_hex, bytes.fromhex(current_block_hash))
        if not is_sig_valid:
            logger.error("merkle_signature_invalid", height=height)
            return False

        return True
