import mmap
import struct
import numpy as np
from multiprocessing import shared_memory
from typing import Optional, Tuple, Dict, Any

from core.config import settings
from core.logging_otel import logger
from core.exceptions import ShmArenaExhaustedException

# C++ SlotHeader layout (64 bytes):
# uint32_t magic (0x4E44544D) -> 4 bytes
# uint32_t slot_id            -> 4 bytes
# uint32_t state              -> 4 bytes (0: FREE, 1: WRITING, 2: READY, 3: READING)
# uint32_t byte_size          -> 4 bytes
# uint64_t timestamp_ns       -> 8 bytes
# uint64_t checksum           -> 8 bytes
# char telemetry_id[32]       -> 32 bytes
SLOT_HEADER_FORMAT = "<IIIIQQ32s"
SLOT_HEADER_SIZE = 64
SLOT_SIZE_BYTES = 1048576  # 1 MB
SLOT_COUNT = 64
ARENA_MAGIC = 0x4E44544D


class ShmTensorReader:
    """Zero-copy tensor reader reading directly from C++ SPSC Shared Memory Arena."""

    def __init__(self, arena_name: Optional[str] = None):
        self.arena_name = (arena_name or settings.SHM_ARENA_NAME).lstrip("/")
        self._shm: Optional[shared_memory.SharedMemory] = None

    def connect(self) -> bool:
        """Attaches to existing POSIX/Win32 shared memory arena created by C++ daemon."""
        try:
            self._shm = shared_memory.SharedMemory(name=self.arena_name, create=False)
            logger.info("shm_attached", arena=self.arena_name, size=self._shm.size)
            return True
        except FileNotFoundError:
            logger.warning("shm_not_found_yet", arena=self.arena_name)
            return False
        except Exception as e:
            logger.error("shm_attach_error", arena=self.arena_name, error=str(e))
            return False

    def close(self) -> None:
        if self._shm is not None:
            self._shm.close()
            self._shm = None

    def read_slot(self, slot_id: int) -> Optional[Tuple[Dict[str, Any], np.ndarray]]:
        """Reads metadata header and zero-copy tensor ndarray view for slot_id."""
        if slot_id < 0 or slot_id >= SLOT_COUNT:
            raise IndexError(f"Slot ID {slot_id} out of bounds [0, {SLOT_COUNT})")

        if self._shm is None:
            if not self.connect():
                return None

        assert self._shm is not None
        # Control block is 64 bytes at offset 0, slots follow
        control_block_size = 64
        offset = control_block_size + (slot_id * SLOT_SIZE_BYTES)

        buf = self._shm.buf[offset : offset + SLOT_SIZE_BYTES]
        header_bytes = bytes(buf[:SLOT_HEADER_SIZE])
        magic, s_id, state, byte_size, ts_ns, checksum, tel_id_bytes = struct.unpack(
            SLOT_HEADER_FORMAT, header_bytes
        )

        if magic != ARENA_MAGIC:
            return None

        # State 2 = READY
        if state != 2:
            return None

        # Clean string
        telemetry_id = tel_id_bytes.split(b"\x00")[0].decode("utf-8", errors="ignore")

        # Zero-copy float32 NumPy array mapped directly to shared memory buffer
        tensor_bytes = buf[SLOT_HEADER_SIZE : SLOT_HEADER_SIZE + byte_size]
        tensor_array = np.frombuffer(tensor_bytes, dtype=np.float32)

        meta = {
            "slot_id": s_id,
            "state": state,
            "byte_size": byte_size,
            "timestamp_ns": ts_ns,
            "checksum": checksum,
            "telemetry_id": telemetry_id,
            "shape": tensor_array.shape,
        }

        return meta, tensor_array

    def release_slot(self, slot_id: int) -> None:
        """Sets slot state back to FREE (0) atomically."""
        if self._shm is None:
            return

        control_block_size = 64
        offset = control_block_size + (slot_id * SLOT_SIZE_BYTES)
        # Update state field (at offset 8 in slot header)
        state_offset = offset + 8
        self._shm.buf[state_offset : state_offset + 4] = struct.pack("<I", 0)
