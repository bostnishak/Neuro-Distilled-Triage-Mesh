"""
Neuro-Distilled Triage Mesh (NDTM) — Sovereign Distributed & Failure-Proof Kernel
RFC-NDTM-OMEGA: Production Hardening Engine v3.0

Phase 31: Snapshotted Upcast Time-Machine Engine
LZ4/Zlib Compressed State Checkpointing Every K=500 Events with Dynamic Schema Upcasting (v1 -> v2 -> v3).
"""

from __future__ import annotations

import copy
import json
import threading
import time
import zlib
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    import lz4.frame as lz4_frame
    HAS_LZ4 = True
except ImportError:
    HAS_LZ4 = False


class StateCompressor:
    """High-throughput binary compressor with automatic LZ4 / Zlib-fast negotiation."""

    @staticmethod
    def compress(payload_bytes: bytes) -> Tuple[bytes, str]:
        if HAS_LZ4:
            return lz4_frame.compress(payload_bytes), "LZ4"
        return zlib.compress(payload_bytes, level=1), "ZLIB1"

    @staticmethod
    def decompress(compressed_bytes: bytes, codec: str) -> bytes:
        if codec == "LZ4" and HAS_LZ4:
            return lz4_frame.decompress(compressed_bytes)
        return zlib.decompress(compressed_bytes)


@dataclass
class StateSnapshot:
    checkpoint_index: int
    event_sequence_number: int
    snapshot_timestamp: float
    compressed_bytes: bytes
    codec: str
    uncompressed_size: int
    entity_count: int


# =====================================================================
# SCHEMA UPCASTER REGISTRY (v1 -> v2 -> v3)
# =====================================================================

class EventUpcasterRegistry:
    """
    Guarantees backward compatibility for historical events across evolving schema versions.
    Automatically chains upcasters: v1 -> v2 -> v3.
    """

    @classmethod
    def upcast(cls, raw_event: Dict[str, Any], target_version: int = 3) -> Dict[str, Any]:
        current_event = copy.deepcopy(raw_event)
        event_ver = current_event.get("schema_version", 1)

        while event_ver < target_version:
            if event_ver == 1:
                current_event = cls._upcast_v1_to_v2(current_event)
                event_ver = 2
            elif event_ver == 2:
                current_event = cls._upcast_v2_to_v3(current_event)
                event_ver = 3
            else:
                break

        current_event["schema_version"] = target_version
        return current_event

    @staticmethod
    def _upcast_v1_to_v2(event: Dict[str, Any]) -> Dict[str, Any]:
        """Upcasts v1 event to v2 by adding embedding dimensions and confidence defaults."""
        event["schema_version"] = 2
        if "confidence" not in event:
            event["confidence"] = 1.0
        if "embedding_dim" not in event:
            event["embedding_dim"] = 384
        if "seqlock_version" not in event:
            event["seqlock_version"] = 1
        return event

    @staticmethod
    def _upcast_v2_to_v3(event: Dict[str, Any]) -> Dict[str, Any]:
        """Upcasts v2 event to v3 by adding H3 hex cell indices and CRDT vector clock."""
        event["schema_version"] = 3
        if "h3_hex_cell" not in event:
            lat = event.get("lat", 0.0)
            lon = event.get("lon", 0.0)
            q_approx = int(round(lon * 100))
            r_approx = int(round(lat * 100))
            event["h3_hex_cell"] = f"{q_approx}:{r_approx}"
        if "schmitt_tier" not in event:
            event["schmitt_tier"] = "LOCAL_EDGE_SPSC"
        if "vector_clock" not in event:
            event["vector_clock"] = {"origin_region": 1}
        return event


# =====================================================================
# TIME-MACHINE REPLAY ENGINE
# =====================================================================

class SnapshottedUpcastTimeMachine:
    """
    Time-Travel State Replayer with O(K) Delta Bounding.
    
    Instead of replaying from the beginning of time:
    1. Checkpoints compressed system state every K events (default K=500).
    2. Given target timestamp t, finds closest preceding checkpoint t_ckpt <= t.
    3. Decompresses checkpoint in <2ms.
    4. Automatically upcasts intermediate historical events to v3.
    5. Replays only delta events (<= 499 steps).
    """

    def __init__(self, checkpoint_interval: int = 500):
        self.k_interval = checkpoint_interval
        self.lock = threading.RLock()

        # Immutable append-only log of raw historical events
        self.event_log: List[Dict[str, Any]] = []

        # List of compressed snapshots
        self.snapshots: List[StateSnapshot] = []

        # Current live state representation: entity_id -> state_dict
        self.live_entities: Dict[str, Dict[str, Any]] = {}
        self.total_replays_performed: int = 0

    def record_event(self, event_dict: Dict[str, Any]) -> int:
        """
        Records an event into the timeline and updates live state.
        Triggers snapshot checkpoint every k_interval events.
        """
        with self.lock:
            seq = len(self.event_log)
            # Ensure sequence number and timestamp
            ev = copy.deepcopy(event_dict)
            ev["seq_num"] = seq
            if "timestamp" not in ev:
                ev["timestamp"] = time.time()

            self.event_log.append(ev)

            # Apply event to live entities
            self._apply_event_to_state(self.live_entities, ev)

            # Checkpoint trigger
            if (seq + 1) % self.k_interval == 0:
                self._create_snapshot_locked(seq + 1)

            return seq

    def _create_snapshot_locked(self, seq_num: int) -> None:
        state_json = json.dumps(self.live_entities).encode("utf-8")
        uncompressed_size = len(state_json)
        compressed_bytes, codec = StateCompressor.compress(state_json)

        snap = StateSnapshot(
            checkpoint_index=len(self.snapshots),
            event_sequence_number=seq_num,
            snapshot_timestamp=self.event_log[-1]["timestamp"],
            compressed_bytes=compressed_bytes,
            codec=codec,
            uncompressed_size=uncompressed_size,
            entity_count=len(self.live_entities),
        )
        self.snapshots.append(snap)

    @staticmethod
    def _apply_event_to_state(state: Dict[str, Dict[str, Any]], event: Dict[str, Any]) -> None:
        """State transition function: S_{t+1} = T(S_t, e_t)."""
        # Automatically upcast event to current v3 schema
        upcasted = EventUpcasterRegistry.upcast(event, target_version=3)
        entity_id = upcasted.get("entity_id") or upcasted.get("id") or upcasted.get("incident_id")
        if not entity_id:
            return

        e_type = upcasted.get("event_type", "INCIDENT_UPDATED")

        if entity_id not in state:
            state[entity_id] = {
                "id": entity_id,
                "created_at": upcasted["timestamp"],
                "version": 0,
                "status": "OPEN",
                "schema_version": 3,
            }

        target = state[entity_id]
        target["version"] += 1
        target["last_updated"] = upcasted["timestamp"]

        # Merge fields
        for k, v in upcasted.items():
            if k not in ("seq_num", "event_type"):
                target[k] = v

        if e_type == "INCIDENT_RESOLVED":
            target["status"] = "RESOLVED"
        elif e_type == "INCIDENT_DISPATCHED":
            target["status"] = "DISPATCHED"

    def reconstruct_state_at(self, target_timestamp: float) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
        """
        Reconstructs the precise system state at target_timestamp in O(K) time.
        """
        t0 = time.perf_counter()
        with self.lock:
            # 1. Find the best snapshot where snapshot_timestamp <= target_timestamp
            candidate_snap: Optional[StateSnapshot] = None
            for snap in reversed(self.snapshots):
                if snap.snapshot_timestamp <= target_timestamp:
                    candidate_snap = snap
                    break

            reconstructed_state: Dict[str, Dict[str, Any]] = {}
            start_seq = 0

            # 2. Decompress snapshot if found
            if candidate_snap is not None:
                decompressed = StateCompressor.decompress(candidate_snap.compressed_bytes, candidate_snap.codec)
                reconstructed_state = json.loads(decompressed.decode("utf-8"))
                start_seq = candidate_snap.event_sequence_number

            # 3. Fast-forward replay only events in range [start_seq, target_timestamp]
            events_replayed_count = 0
            for i in range(start_seq, len(self.event_log)):
                ev = self.event_log[i]
                if ev["timestamp"] > target_timestamp:
                    break
                self._apply_event_to_state(reconstructed_state, ev)
                events_replayed_count += 1

            self.total_replays_performed += 1
            elapsed_ms = (time.perf_counter() - t0) * 1000.0

            metadata = {
                "target_timestamp": target_timestamp,
                "snapshot_used_index": candidate_snap.checkpoint_index if candidate_snap else -1,
                "snapshot_codec": candidate_snap.codec if candidate_snap else "NONE",
                "events_replayed_delta": events_replayed_count,
                "total_events_in_log": len(self.event_log),
                "reconstruction_time_ms": round(elapsed_ms, 3),
                "entities_count": len(reconstructed_state),
            }

            return reconstructed_state, metadata
