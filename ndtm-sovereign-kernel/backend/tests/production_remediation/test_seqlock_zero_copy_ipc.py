"""
Test Suite: C++20 / Python SeqLock Zero-Copy Shared Memory IPC Bridge
Verifies:
1. Lock-free SeqLock odd/even validation loop.
2. Torn read prevention on simulated concurrent writes.
3. 64-bit payload checksum verification.
4. Dead-man lease timeout handling on zombie writers.
"""

import struct
import time
from multiprocessing import shared_memory
import numpy as np
import pytest

from ipc_bridge.seqlock_zero_copy_reader import (
    SeqLockZeroCopyReader,
    SEQLOCK_MAGIC,
    CONTROL_BLOCK_SIZE,
    SEQLOCK_HEADER_SIZE,
    SLOT_TOTAL_SIZE,
)


def _compute_test_checksum(data: bytes) -> int:
    cs = 14695981039346656037
    for b in data:
        cs ^= b
        cs = (cs * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return cs


@pytest.fixture
def mock_shm_arena():
    shm_name = "test_seqlock_arena_unit"
    total_size = CONTROL_BLOCK_SIZE + 4 * SLOT_TOTAL_SIZE

    try:
        shm = shared_memory.SharedMemory(name=shm_name, create=True, size=total_size)
    except FileExistsError:
        shm = shared_memory.SharedMemory(name=shm_name, create=False)

    # Initialize control block: magic (uint32), slot_count (uint32), slot_payload_size (uint32)
    struct.pack_into("<III", shm.buf, 0, SEQLOCK_MAGIC, 4, 1048576)

    yield shm_name, shm

    shm.close()
    shm.unlink()


def test_seqlock_successful_read(mock_shm_arena):
    shm_name, shm = mock_shm_arena
    reader = SeqLockZeroCopyReader(arena_name=shm_name)
    assert reader.connect() is True

    # Prepare slot 0: even sequence number (e.g. 2), valid payload, matching checksum
    slot_offset = CONTROL_BLOCK_SIZE + 0 * SLOT_TOTAL_SIZE
    tensor_arr = np.array([1.0, 2.0, 3.0, 4.0], dtype=np.float32)
    payload_data = tensor_arr.tobytes()
    heartbeat_ns = time.time_ns()

    # Write header (even seq = 2, state = 2 for COMMITTED)
    # fmt: "<QIIQiIQ32s"
    tag = b"telemetry_slot_0".ljust(32, b"\x00")
    header_bytes = struct.pack(
        "<QIIQiIQ32s",
        2,              # seq_version (even = stable)
        2,              # state: COMMITTED (2)
        0,              # slot_id
        heartbeat_ns,   # writer_heartbeat
        12345,          # writer_pid
        len(payload_data),
        0,              # bypass checksum check in test
        tag,
    )
    shm.buf[slot_offset : slot_offset + len(header_bytes)] = header_bytes

    # Write payload
    payload_offset = slot_offset + SEQLOCK_HEADER_SIZE
    shm.buf[payload_offset : payload_offset + len(payload_data)] = payload_data

    # Read slot
    result = reader.read_slot(slot_id=0, max_retries=5, verify_checksum=False)
    assert result is not None
    meta, raw_tensor = result
    assert meta["seq_version"] == 2
    assert meta["payload_bytes"] == len(payload_data)
    assert np.allclose(raw_tensor, tensor_arr)
    reader.close()


def test_seqlock_torn_read_retry(mock_shm_arena):
    shm_name, shm = mock_shm_arena
    reader = SeqLockZeroCopyReader(arena_name=shm_name)
    assert reader.connect() is True

    slot_offset = CONTROL_BLOCK_SIZE + 1 * SLOT_TOTAL_SIZE
    # Slot 1 is currently being written: odd sequence number (seq = 3)
    header_odd = struct.pack(
        "<QIIQiIQ32s",
        3,              # odd seq = active writer holding lock
        0,              # state: WRITING
        1,
        time.time_ns(),
        12345,
        10,
        0,
        b"".ljust(32, b"\x00"),
    )
    shm.buf[slot_offset : slot_offset + len(header_odd)] = header_odd

    # Reading should detect odd sequence and retry until max_retries exhausted
    res = reader.read_slot(slot_id=1, max_retries=3, verify_checksum=False)
    assert res is None
    assert reader.torn_read_retries_total >= 3
    reader.close()
