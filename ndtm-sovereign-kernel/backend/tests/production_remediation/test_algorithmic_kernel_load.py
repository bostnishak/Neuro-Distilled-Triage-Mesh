"""
NDTM-9000 Sovereign Kernel — Comprehensive Algorithmic Engines Load Benchmark
Tests core mathematical, cryptographic, and concurrency engines under extreme load.
"""

import time
import struct
import threading
import statistics
import numpy as np
import pytest
from multiprocessing import shared_memory

from engines_v3_hardened.markovian_h3_hawkes_engine import MarkovianH3HawkesEngine, HawkesIncidentEvent
from engines_v3_hardened.ledoit_wolf_cholesky_ood import LedoitWolfCholeskyOODDetector
from engines_v3_hardened.isolated_anytime_z3_lns import (
    SubprocessIsolatedAnytimeZ3LNSDispatcher,
    IncidentSummary,
    TeamSummary,
)
from engines_v3_hardened.crdt_multiregion_replicator import (
    ActiveActiveMeshReplicator,
    PNCounter,
    VectorClock,
    LWWElementSet,
)
from ipc_bridge.seqlock_zero_copy_reader import (
    SeqLockZeroCopyReader,
    SEQLOCK_MAGIC,
    SEQLOCK_SLOT_COUNT,
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


def test_hawkes_point_process_high_throughput_load():
    """Benchmarking 20,000 spatial incident ingestions into Hawkes Markovian H3 engine."""
    engine = MarkovianH3HawkesEngine(hex_radius_meters=250.0)
    num_events = 20000
    
    start_time = time.perf_counter()
    base_t = time.time()
    
    for i in range(num_events):
        lat = 41.0082 + (i % 100) * 0.001
        lon = 28.9784 + ((i // 100) % 100) * 0.001
        ev = HawkesIncidentEvent(
            event_id=f"inc_{i}",
            timestamp=base_t + (i * 0.01),
            lat=lat,
            lon=lon,
            category="FIRE" if i % 2 == 0 else "HAZMAT",
            severity=1.0 + (i % 5) * 0.2,
        )
        engine.ingest_event(ev)
        
    duration = time.perf_counter() - start_time
    throughput = num_events / duration
    
    heatmap = engine.export_geojson_heatmap()
    print(f"\n[Hawkes Load] Processed {num_events} events in {duration:.3f}s -> Throughput: {throughput:,.1f} events/sec")
    print(f"[Hawkes Load] Active cells tracked: {len(heatmap['features'])}")
    
    assert throughput > 2000.0, f"Hawkes throughput too low: {throughput} ev/s"
    assert len(heatmap["features"]) > 0


def test_ledoit_wolf_cholesky_ood_streaming_load():
    """Benchmarking Ledoit-Wolf OOD Mahalanobis scoring under 2,000 384-D vector streams."""
    p = 384
    np.random.seed(42)
    reference_data = np.random.randn(200, p).astype(np.float32)
    
    ood = LedoitWolfCholeskyOODDetector(embedding_dim=p)
    ood.fit(reference_data)
    
    test_samples = np.random.randn(2000, p).astype(np.float32)
    latencies = []
    
    for i in range(len(test_samples)):
        sample = test_samples[i]
        t0 = time.perf_counter()
        res = ood.evaluate(sample)
        latencies.append((time.perf_counter() - t0) * 1000.0)  # ms
        
    p50 = statistics.median(latencies)
    p95 = statistics.quantiles(latencies, n=20)[18]
    p99 = statistics.quantiles(latencies, n=100)[98]
    total_time = sum(latencies) / 1000.0
    throughput = len(test_samples) / total_time
    
    print(f"\n[Ledoit-Wolf Load] 2,000 384-D samples scored in {total_time:.3f}s -> {throughput:,.1f} samples/sec")
    print(f"[Ledoit-Wolf Load] Latency P50: {p50:.3f}ms | P95: {p95:.3f}ms | P99: {p99:.3f}ms")
    
    assert p95 < 5.0, f"P95 latency too high: {p95:.3f}ms"
    assert throughput > 500.0


def test_seqlock_zero_copy_concurrency_race():
    """Testing lock-free SeqLock reading while writer updates at 10,000 writes/sec."""
    shm_name = "test_seqlock_race_bench"
    total_size = CONTROL_BLOCK_SIZE + SEQLOCK_SLOT_COUNT * SLOT_TOTAL_SIZE
    try:
        shm = shared_memory.SharedMemory(name=shm_name, create=True, size=total_size)
    except FileExistsError:
        shm = shared_memory.SharedMemory(name=shm_name, create=False)

    try:
        struct.pack_into("<III", shm.buf, 0, SEQLOCK_MAGIC, SEQLOCK_SLOT_COUNT, 1048576)
        reader = SeqLockZeroCopyReader(arena_name=shm_name)
        assert reader.connect() is True

        tensor_arr = np.array([1.0, 2.0, 3.0, 4.0], dtype=np.float32)
        payload_bytes = tensor_arr.tobytes()
        checksum = _compute_test_checksum(payload_bytes)
        slot_offset = CONTROL_BLOCK_SIZE + 0 * SLOT_TOTAL_SIZE

        stop_event = threading.Event()
        write_count = 0
        clean_reads = 0

        def writer_thread():
            nonlocal write_count
            seq = 0
            while not stop_event.is_set() and write_count < 10000:
                seq += 1
                struct.pack_into("<Q", shm.buf, slot_offset, seq)
                shm.buf[slot_offset + SEQLOCK_HEADER_SIZE : slot_offset + SEQLOCK_HEADER_SIZE + len(payload_bytes)] = payload_bytes
                seq += 1
                struct.pack_into(
                    "<QIIQiIQ32s",
                    shm.buf,
                    slot_offset,
                    seq,
                    2,  # State COMMITTED = 2
                    0,  # slot_id
                    time.monotonic_ns(),
                    100,
                    len(payload_bytes),
                    checksum,
                    b"bench_slot_0".ljust(32, b"\x00"),
                )
                write_count += 1
                time.sleep(0.000001)

        def reader_thread():
            nonlocal clean_reads
            r = SeqLockZeroCopyReader(arena_name=shm_name)
            r.connect()
            while not stop_event.is_set():
                res = r.read_slot(slot_id=0, max_retries=10, verify_checksum=True)
                if res is not None:
                    clean_reads += 1
                time.sleep(0.000005)

        t_writer = threading.Thread(target=writer_thread)
        t_readers = [threading.Thread(target=reader_thread) for _ in range(2)]

        t0 = time.perf_counter()
        t_writer.start()
        for r in t_readers:
            r.start()

        t_writer.join(timeout=5.0)
        stop_event.set()
        for r in t_readers:
            r.join(timeout=1.0)

        elapsed = time.perf_counter() - t0
        print(f"\n[SeqLock Race] Writes: {write_count} | Clean Reads: {clean_reads} in {elapsed:.3f}s")
        assert write_count >= 1000
        assert clean_reads > 50
    finally:
        shm.close()
        shm.unlink()


def test_anytime_hungarian_high_load_dispatch():
    """Benchmarking 100 concurrent dispatch batches under tight micro-deadlines."""
    dispatcher = SubprocessIsolatedAnytimeZ3LNSDispatcher(z3_timeout_ms=50)
    
    incidents = [
        IncidentSummary(
            id=f"inc_{i}",
            category="FIRE" if i % 2 == 0 else "HAZMAT",
            urgency="CRITICAL" if i % 3 == 0 else "HIGH",
            lat=41.01 + (i * 0.002),
            lon=28.98 + (i * 0.002),
            criticality=2.0 if i % 3 == 0 else 1.0,
        )
        for i in range(12)
    ]
    teams = [
        TeamSummary(
            id=f"team_{j}",
            specialization="FIRE" if j % 2 == 0 else "HAZMAT",
            burnout_index=0.1 * j,
            lat=41.00 + (j * 0.003),
            lon=28.97 + (j * 0.003),
            is_available=True,
        )
        for j in range(8)
    ]
    
    latencies = []
    iterations = 100
    t0 = time.perf_counter()
    
    for _ in range(iterations):
        t_start = time.perf_counter()
        res = dispatcher.dispatch(incidents, teams, sla_deadline_ms=25)
        latencies.append((time.perf_counter() - t_start) * 1000.0)
        assert len(res.assignments) > 0
        
    total_dur = time.perf_counter() - t0
    p50 = statistics.median(latencies)
    p95 = statistics.quantiles(latencies, n=20)[18]
    p99 = statistics.quantiles(latencies, n=100)[98]
    throughput = iterations / total_dur
    
    print(f"\n[Dispatch Load] {iterations} batches (12x8) solved in {total_dur:.3f}s -> {throughput:,.1f} dispatches/sec")
    print(f"[Dispatch Load] Latency P50: {p50:.2f}ms | P95: {p95:.2f}ms | P99: {p99:.2f}ms")
    
    assert p95 < 25.0, f"P95 dispatch latency too high: {p95:.2f}ms"


def test_crdt_mesh_concurrent_mutation_load():
    """Benchmarking 3,000 distributed CRDT state mutations across 3 regions."""
    r_ist = ActiveActiveMeshReplicator("tr-marmara-ist")
    r_ank = ActiveActiveMeshReplicator("tr-central-ank")
    r_izm = ActiveActiveMeshReplicator("tr-aegean-izm")
    replicators = [r_ist, r_ank, r_izm]
    num_mutations = 3000
    
    t0 = time.perf_counter()
    for i in range(num_mutations):
        rep = replicators[i % 3]
        rep.local_open_incident(f"inc_{i}")
        
    duration = time.perf_counter() - t0
    throughput = num_mutations / duration
    
    # Delta exchange
    delta_ist = r_ist.export_sync_delta()
    delta_ank = r_ank.export_sync_delta()
    delta_izm = r_izm.export_sync_delta()
    
    r_ist.ingest_sync_delta(delta_ank)
    r_ist.ingest_sync_delta(delta_izm)
    
    status_ist = r_ist.get_mesh_status()
    print(f"\n[CRDT Mesh Load] {num_mutations} mutations in {duration:.3f}s -> {throughput:,.1f} ops/sec")
    print(f"[CRDT Mesh Load] Region IST converged incidents count: {status_ist['active_incidents_count']}")
    
    assert throughput > 1000.0
    assert status_ist["active_incidents_count"] == num_mutations
