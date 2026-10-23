"""
Neuro-Distilled Triage Mesh (NDTM) — Sovereign Distributed & Failure-Proof Kernel
RFC-NDTM-OMEGA: Production Hardening Engine v3.0

Phase 31: Multi-Region CRDT State Replicator
Active-Active Conflict-Free Replicated Data Types (VectorClock, PNCounter, LWWElementSet)
Guarantees Strong Eventual Consistency across WAN Partitions.
"""

from __future__ import annotations

import copy
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass
class VectorClock:
    """Logical causality clock across distributed geographic regions."""
    clock: Dict[str, int] = field(default_factory=dict)

    def increment(self, region_id: str) -> None:
        self.clock[region_id] = self.clock.get(region_id, 0) + 1

    def merge(self, other: VectorClock) -> VectorClock:
        """Commutative, associative, idempotent join-semilattice merge: max(c1, c2)."""
        merged_clock = dict(self.clock)
        for r_id, count in other.clock.items():
            merged_clock[r_id] = max(merged_clock.get(r_id, 0), count)
        return VectorClock(clock=merged_clock)

    def happens_before(self, other: VectorClock) -> bool:
        """Returns True if self strictly precedes other in causal history."""
        all_regions = set(self.clock.keys()) | set(other.clock.keys())
        has_strictly_smaller = False
        for r in all_regions:
            c_self = self.clock.get(r, 0)
            c_other = other.clock.get(r, 0)
            if c_self > c_other:
                return False
            if c_self < c_other:
                has_strictly_smaller = True
        return has_strictly_smaller

    def is_concurrent_with(self, other: VectorClock) -> bool:
        """Returns True if neither clock causally dominates the other (concurrent edit)."""
        return (not self.happens_before(other)) and (not other.happens_before(self)) and (self.clock != other.clock)

    def to_dict(self) -> Dict[str, int]:
        return dict(self.clock)


@dataclass
class PNCounter:
    """
    Positive-Negative Counter CRDT.
    Supports concurrent increment and decrement across regions with guaranteed convergence.
    """
    p_map: Dict[str, int] = field(default_factory=dict)
    n_map: Dict[str, int] = field(default_factory=dict)

    def increment(self, region_id: str, value: int = 1) -> None:
        if value < 0:
            raise ValueError("Use decrement for negative values")
        self.p_map[region_id] = self.p_map.get(region_id, 0) + value

    def decrement(self, region_id: str, value: int = 1) -> None:
        if value < 0:
            raise ValueError("Use increment for negative values")
        self.n_map[region_id] = self.n_map.get(region_id, 0) + value

    @property
    def value(self) -> int:
        return sum(self.p_map.values()) - sum(self.n_map.values())

    def merge(self, other: PNCounter) -> PNCounter:
        """Semilattice join: coordinate-wise maximum for both P and N vectors."""
        all_p = set(self.p_map.keys()) | set(other.p_map.keys())
        all_n = set(self.n_map.keys()) | set(other.n_map.keys())

        merged_p = {r: max(self.p_map.get(r, 0), other.p_map.get(r, 0)) for r in all_p}
        merged_n = {r: max(self.n_map.get(r, 0), other.n_map.get(r, 0)) for r in all_n}
        return PNCounter(p_map=merged_p, n_map=merged_n)

    def to_dict(self) -> Dict[str, Any]:
        return {"value": self.value, "p": dict(self.p_map), "n": dict(self.n_map)}


@dataclass
class LWWElementSet:
    """
    Last-Write-Wins Element Set CRDT.
    Tracks additions and removals with physical timestamp + regional tie-breaker.
    """
    # element -> (timestamp_seconds, region_id)
    add_set: Dict[str, Tuple[float, str]] = field(default_factory=dict)
    remove_set: Dict[str, Tuple[float, str]] = field(default_factory=dict)

    def add(self, element: str, region_id: str, timestamp: Optional[float] = None) -> None:
        ts = timestamp if timestamp is not None else time.time()
        prev = self.add_set.get(element)
        if prev is None or (ts, region_id) > prev:
            self.add_set[element] = (ts, region_id)

    def remove(self, element: str, region_id: str, timestamp: Optional[float] = None) -> None:
        ts = timestamp if timestamp is not None else time.time()
        prev = self.remove_set.get(element)
        if prev is None or (ts, region_id) > prev:
            self.remove_set[element] = (ts, region_id)

    def contains(self, element: str) -> bool:
        if element not in self.add_set:
            return False
        if element not in self.remove_set:
            return True
        add_tuple = self.add_set[element]
        remove_tuple = self.remove_set[element]
        # Element is present if add record is strictly newer than remove record
        return add_tuple > remove_tuple

    def read_all(self) -> Set[str]:
        return {e for e in self.add_set.keys() if self.contains(e)}

    def merge(self, other: LWWElementSet) -> LWWElementSet:
        """Semilattice join: max timestamp per element across both add and remove sets."""
        merged_add = dict(self.add_set)
        for elem, val in other.add_set.items():
            if elem not in merged_add or val > merged_add[elem]:
                merged_add[elem] = val

        merged_rem = dict(self.remove_set)
        for elem, val in other.remove_set.items():
            if elem not in merged_rem or val > merged_rem[elem]:
                merged_rem[elem] = val

        return LWWElementSet(add_set=merged_add, remove_set=merged_rem)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "active_elements": sorted(list(self.read_all())),
            "add_count": len(self.add_set),
            "remove_count": len(self.remove_set),
        }


@dataclass
class RegionalCRDTState:
    region_id: str
    vector_clock: VectorClock = field(default_factory=VectorClock)
    incident_counter: PNCounter = field(default_factory=PNCounter)
    active_incidents_set: LWWElementSet = field(default_factory=LWWElementSet)
    dispatched_teams_set: LWWElementSet = field(default_factory=LWWElementSet)


class ActiveActiveMeshReplicator:
    """
    Sovereign Multi-Region Coordinator.
    Manages regional replica states and simulates or coordinates WAN packet replication.
    """

    def __init__(self, local_region_id: str = "us-west-1"):
        self.local_region = local_region_id
        self.lock = threading.RLock()
        self.state = RegionalCRDTState(region_id=local_region_id)
        self.sync_packets_sent: int = 0
        self.sync_packets_received: int = 0

    def local_open_incident(self, incident_id: str) -> None:
        """Opens a new incident in the local region."""
        with self.lock:
            self.state.vector_clock.increment(self.local_region)
            self.state.incident_counter.increment(self.local_region, 1)
            self.state.active_incidents_set.add(incident_id, self.local_region)

    def local_resolve_incident(self, incident_id: str) -> None:
        """Resolves an incident in the local region."""
        with self.lock:
            self.state.vector_clock.increment(self.local_region)
            self.state.incident_counter.decrement(self.local_region, 1)
            self.state.active_incidents_set.remove(incident_id, self.local_region)

    def local_assign_team(self, team_id: str) -> None:
        with self.lock:
            self.state.vector_clock.increment(self.local_region)
            self.state.dispatched_teams_set.add(team_id, self.local_region)

    def export_sync_delta(self) -> Dict[str, Any]:
        """Generates a delta packet to broadcast across WAN to remote regions."""
        with self.lock:
            self.sync_packets_sent += 1
            return {
                "source_region": self.local_region,
                "exported_at": time.time(),
                "vector_clock": self.state.vector_clock.to_dict(),
                "incident_counter": self.state.incident_counter.to_dict(),
                "active_incidents_set": {
                    "add": {k: list(v) for k, v in self.state.active_incidents_set.add_set.items()},
                    "remove": {k: list(v) for k, v in self.state.active_incidents_set.remove_set.items()},
                },
                "dispatched_teams_set": {
                    "add": {k: list(v) for k, v in self.state.dispatched_teams_set.add_set.items()},
                    "remove": {k: list(v) for k, v in self.state.dispatched_teams_set.remove_set.items()},
                },
            }

    def ingest_sync_delta(self, delta_packet: Dict[str, Any]) -> None:
        """Ingests a remote delta packet and executes semilattice state merge."""
        with self.lock:
            # 1. Merge VectorClock
            remote_vc = VectorClock(clock=delta_packet.get("vector_clock", {}))
            self.state.vector_clock = self.state.vector_clock.merge(remote_vc)

            # 2. Merge PNCounter
            p_data = delta_packet.get("incident_counter", {})
            remote_pn = PNCounter(p_map=p_data.get("p", {}), n_map=p_data.get("n", {}))
            self.state.incident_counter = self.state.incident_counter.merge(remote_pn)

            # 3. Merge LWW Active Incidents
            raw_inc = delta_packet.get("active_incidents_set", {})
            remote_inc_add = {k: (v[0], v[1]) for k, v in raw_inc.get("add", {}).items()}
            remote_inc_rem = {k: (v[0], v[1]) for k, v in raw_inc.get("remove", {}).items()}
            remote_inc_set = LWWElementSet(add_set=remote_inc_add, remove_set=remote_inc_rem)
            self.state.active_incidents_set = self.state.active_incidents_set.merge(remote_inc_set)

            # 4. Merge LWW Dispatched Teams
            raw_teams = delta_packet.get("dispatched_teams_set", {})
            remote_team_add = {k: (v[0], v[1]) for k, v in raw_teams.get("add", {}).items()}
            remote_team_rem = {k: (v[0], v[1]) for k, v in raw_teams.get("remove", {}).items()}
            remote_team_set = LWWElementSet(add_set=remote_team_add, remove_set=remote_team_rem)
            self.state.dispatched_teams_set = self.state.dispatched_teams_set.merge(remote_team_set)

            self.sync_packets_received += 1

    def get_mesh_status(self) -> Dict[str, Any]:
        with self.lock:
            return {
                "local_region": self.local_region,
                "vector_clock": self.state.vector_clock.to_dict(),
                "active_incidents_count": self.state.incident_counter.value,
                "active_incident_ids": sorted(list(self.state.active_incidents_set.read_all())),
                "dispatched_team_ids": sorted(list(self.state.dispatched_teams_set.read_all())),
                "sync_packets_sent": self.sync_packets_sent,
                "sync_packets_received": self.sync_packets_received,
            }
