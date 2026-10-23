# ADR-0002: POSIX Shared Memory and Lock-Free SeqLock Epoch IPC

## Status
Accepted

## Context
Real-time sensor telemetry (acoustic FFT Mel-frequency spectrograms, optical Laplacian edge variances, vibration sensor streams) must be ingested at 16,000 Hz from edge C++ hardware daemons into the Python sovereign triage mesh with sub-millisecond latency. 

Standard IPC mechanisms such as TCP loopback sockets, Unix domain sockets, or named pipes suffer from kernel context switches, double memory copying (kernel buffer $\leftrightarrow$ user buffer), and serialization overhead.

## Decision
We implement a zero-copy shared memory architecture:
1. **Shared Memory Segment:** Memory-mapped arena (`shm_open` on POSIX with `0600` permissions; `CreateFileMappingA` / `MapViewOfFile` on Windows with `intptr_t` 64-bit handle safety).
2. **Lock-Free Concurrency via SeqLock:**
   - Single-writer, multiple-reader (SWMR) protocol.
   - Slot versions incremented before and after writing. An odd version denotes an active writer; an even version denotes committed data.
   - Readers verify $v_1 == v_2 \pmod 2 == 0$. If torn, readers re-try without blocking or taking mutexes.
3. **Dead-Man Lease Watchdog:**
   - If a C++ writer crashes mid-write holding an odd sequence lock, readers observe heartbeat expiration (50ms lease) and force-reclaim the slot.
   - SPSC atomic ring buffers use modular distance arithmetic `(tail - head)` to operate reliably through 64-bit integer wrap-around.

## Consequences
- **Positive:** Zero kernel context switches during telemetry transfer; read latency < 0.2ms; eliminates IPC starvation.
- **Negative:** Requires strict struct padding, byte-alignment (`#pragma pack(push, 1)` or explicit cache-line alignment), and 64-bit endian consistency.
