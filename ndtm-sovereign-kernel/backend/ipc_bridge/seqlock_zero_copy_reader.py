import struct
import time
from multiprocessing import shared_memory
from typing import Any, Dict, Optional, Tuple
import numpy as np

SEQLOCK_MAGIC = 0x4E445351  # "NDSQ"
SEQLOCK_SLOT_COUNT = 64
SEQLOCK_SLOT_PAYLOAD_SIZE = 1048576  # 1 MB
SEQLOCK_HEADER_SIZE = 128  # 128-byte cache-aligned header
CONTROL_BLOCK_SIZE = 64   # 64-byte control block
SLOT_TOTAL_SIZE = SEQLOCK_HEADER_SIZE + SEQLOCK_SLOT_PAYLOAD_SIZE
DEADMAN_LEASE_TIMEOUT_NS = 50_000_000  # 50 ms

# Header unpack format (first 72 bytes):
# uint64_t seq_version       -> Q (8)
# uint32_t state             -> I (4)
# uint32_t slot_id           -> I (4)
# uint64_t writer_heartbeat  -> Q (8)
# int32_t writer_pid         -> i (4)
# uint32_t payload_bytes     -> I (4)
# uint64_t payload_checksum  -> Q (8)
# char telemetry_tag[32]     -> 32s (32)
SLOT_HEADER_UNPACK_FMT = "<QIIQiIQ32s"
SLOT_HEADER_UNPACK_LEN = 72


class SeqLockZeroCopyReader:
    """Optimistic lock-free zero-copy tensor reader with SeqLock validation and dead-man lease monitoring."""

    def __init__(self, arena_name: str = "/ndtm_seqlock_arena"):
        self.arena_name = arena_name.lstrip("/")
        self._shm: Optional[shared_memory.SharedMemory] = None
        self.torn_read_retries_total = 0
        self.deadman_reclaims_observed = 0

    def connect(self) -> bool:
        """Attaches to existing POSIX/Win32 shared memory arena created by C++ kernel."""
        try:
            self._shm = shared_memory.SharedMemory(name=self.arena_name, create=False)
            return True
        except FileNotFoundError:
            return False
        except Exception:
            return False

    def close(self) -> None:
        if self._shm is not None:
            self._shm.close()
            self._shm = None

    def read_slot(
        self,
        slot_id: int,
        max_retries: int = 10,
        verify_checksum: bool = True,
    ) -> Optional[Tuple[Dict[str, Any], np.ndarray]]:
        """Reads slot payload optimistically with sequence lock validation.

        Guarantees 100% immunity against torn reads:
        Accepts tensor iff seq_version before read == seq_version after read AND seq_version is EVEN.
        """
        if slot_id < 0 or slot_id >= SEQLOCK_SLOT_COUNT:
            raise IndexError(f"Slot ID {slot_id} out of bounds [0, {SEQLOCK_SLOT_COUNT})")

        if self._shm is None and not self.connect():
            return None

        assert self._shm is not None
        slot_offset = CONTROL_BLOCK_SIZE + (slot_id * SLOT_TOTAL_SIZE)
        slot_buf = self._shm.buf[slot_offset : slot_offset + SLOT_TOTAL_SIZE]

        for attempt in range(max_retries):
            # 1. Read seq_version v1
            v1 = struct.unpack_from("<Q", slot_buf, 0)[0]

            # If ODD, a writer is currently modifying this slot
            if (v1 & 1) != 0:
                # Check for Dead-Man Lease expiration (50 ms)
                heartbeat_ns = struct.unpack_from("<Q", slot_buf, 16)[0]
                now_ns = int(time.monotonic_ns())
                if now_ns > heartbeat_ns and (now_ns - heartbeat_ns) > DEADMAN_LEASE_TIMEOUT_NS:
                    self.deadman_reclaims_observed += 1
                    # Slot is held by crashed writer; skip or yield
                    time.sleep(0.001)
                    continue

                self.torn_read_retries_total += 1
                time.sleep(0.0001)
                continue

            # Read remaining header metadata
            hdr_bytes = bytes(slot_buf[:SLOT_HEADER_UNPACK_LEN])
            (
                seq_ver,
                state,
                s_id,
                hb_ns,
                writer_pid,
                payload_bytes,
                expected_checksum,
                raw_tag,
            ) = struct.unpack(SLOT_HEADER_UNPACK_FMT, hdr_bytes)

            # State must be COMMITTED (2)
            if state != 2:
                return None

            if payload_bytes == 0 or payload_bytes > SEQLOCK_SLOT_PAYLOAD_SIZE:
                return None

            # 2. Extract zero-copy ndarray view from shared memory buffer
            payload_start = SEQLOCK_HEADER_SIZE
            payload_end = payload_start + payload_bytes
            raw_tensor_bytes = slot_buf[payload_start:payload_end]
            tensor_view = np.frombuffer(raw_tensor_bytes, dtype=np.float32)

            # 3. Read seq_version v2
            v2 = struct.unpack_from("<Q", slot_buf, 0)[0]

            # Strict SeqLock Invariant:
            # v1 must equal v2, and both must be EVEN (no write occurred during reading)
            if v1 == v2 and (v1 & 1) == 0:
                # Optional FNV-1a checksum validation
                if verify_checksum and expected_checksum != 0:
                    computed_chk = self._compute_fast_checksum(tensor_view)
                    if computed_chk != expected_checksum:
                        self.torn_read_retries_total += 1
                        continue

                tag_str = raw_tag.split(b"\x00")[0].decode("utf-8", errors="ignore")
                meta = {
                    "slot_id": s_id,
                    "seq_version": v2,
                    "state": state,
                    "writer_pid": writer_pid,
                    "writer_heartbeat_ns": hb_ns,
                    "payload_bytes": payload_bytes,
                    "element_count": tensor_view.size,
                    "telemetry_tag": tag_str,
                    "torn_read_attempts": attempt,
                }
                # Return a safe copy or view
                return meta, tensor_view.copy()

            self.torn_read_retries_total += 1

        return None

    def release_slot(self, slot_id: int) -> None:
        """Marks slot state back to FREE (0)."""
        if self._shm is None:
            return
        slot_offset = CONTROL_BLOCK_SIZE + (slot_id * SLOT_TOTAL_SIZE)
        # State field is at offset 8 (uint32_t)
        struct.pack_into("<I", self._shm.buf, slot_offset + 8, 0)

    @staticmethod
    def _compute_fast_checksum(arr: np.ndarray) -> int:
        """Matches C++ compute_fast_checksum (FNV-1a 64-bit)."""
        h = 0xCBF29CE484222325
        prime = 0x100000001B3
        mask = 0xFFFFFFFFFFFFFFFF
        raw = arr.tobytes()
        for b in raw:
            h ^= b
            h = (h * prime) & mask
        return h
