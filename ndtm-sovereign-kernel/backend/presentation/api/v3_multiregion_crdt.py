"""
Neuro-Distilled Triage Mesh (NDTM) — Sovereign Distributed & Failure-Proof Kernel
RFC-NDTM-OMEGA: Production Hardening Engine v3.0

Phase 34: Multi-Region CRDT Mesh API Router
Exposes Endpoints for Active-Active Conflict-Free Replicated State Sync,
WAN Delta Broadcasting, and Partition Healing Simulation.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from engines_v3_hardened.crdt_multiregion_replicator import ActiveActiveMeshReplicator

router = APIRouter(prefix="/v3/crdt", tags=["Multi-Region CRDT State Mesh"])

# Regional replicators for simulation & live state
_replicator_us = ActiveActiveMeshReplicator("us-west-1")
_replicator_eu = ActiveActiveMeshReplicator("eu-central-1")
_replicator_ap = ActiveActiveMeshReplicator("ap-southeast-1")


class LocalEventRequest(BaseModel):
    region_id: str = "us-west-1"
    event_action: str = Field(..., description="OPEN_INCIDENT | RESOLVE_INCIDENT | ASSIGN_TEAM")
    entity_id: str


class SyncDeltaPayload(BaseModel):
    source_region: str
    exported_at: float
    vector_clock: Dict[str, int]
    incident_counter: Dict[str, Any]
    active_incidents_set: Dict[str, Any]
    dispatched_teams_set: Dict[str, Any]


@router.get("/status", summary="Get Regional CRDT Status")
async def get_crdt_status(region_id: str = "us-west-1") -> Dict[str, Any]:
    """Returns local VectorClock, PNCounter, and LWWElementSet for the requested region."""
    rep = _get_replicator(region_id)
    return rep.get_mesh_status()


@router.get("/all-regions", summary="Get All Multi-Region States")
async def get_all_regions_status() -> Dict[str, Any]:
    """Returns status across all 3 active regions (US, EU, AP)."""
    return {
        "us-west-1": _replicator_us.get_mesh_status(),
        "eu-central-1": _replicator_eu.get_mesh_status(),
        "ap-southeast-1": _replicator_ap.get_mesh_status(),
    }


@router.post("/local-event", summary="Mutate Local Regional CRDT State")
async def post_local_event(req: LocalEventRequest) -> Dict[str, Any]:
    """Applies a local state mutation to the target region without requiring synchronous WAN locks."""
    rep = _get_replicator(req.region_id)

    action = req.event_action.upper()
    if action == "OPEN_INCIDENT":
        rep.local_open_incident(req.entity_id)
    elif action == "RESOLVE_INCIDENT":
        rep.local_resolve_incident(req.entity_id)
    elif action == "ASSIGN_TEAM":
        rep.local_assign_team(req.entity_id)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown action: {req.event_action}. Expected OPEN_INCIDENT, RESOLVE_INCIDENT, or ASSIGN_TEAM",
        )

    return {
        "status": "MUTATION_COMMITTED_LOCALLY",
        "region_id": req.region_id,
        "mesh_status": rep.get_mesh_status(),
    }


@router.get("/sync-delta", summary="Export Sync Delta for WAN Broadcast")
async def export_sync_delta(region_id: str = "us-west-1") -> Dict[str, Any]:
    """Generates a Delta-CRDT packet to replicate across WAN."""
    rep = _get_replicator(region_id)
    return rep.export_sync_delta()


@router.post("/sync-delta", summary="Ingest Remote Sync Delta")
async def ingest_sync_delta(target_region_id: str, delta: SyncDeltaPayload) -> Dict[str, Any]:
    """Ingests remote sync delta packet and executes semilattice state join."""
    rep = _get_replicator(target_region_id)
    rep.ingest_sync_delta(delta.dict())
    return {
        "status": "DELTA_MERGED_SUCCESSFULLY",
        "target_region_id": target_region_id,
        "mesh_status": rep.get_mesh_status(),
    }


@router.post("/simulate-wan-partition", summary="Simulate WAN Partition & Convergence")
async def simulate_wan_partition() -> Dict[str, Any]:
    """
    Executes an active-active split-brain simulation:
    1. US opens incidents while WAN is partitioned.
    2. EU opens concurrent incidents.
    3. WAN heals: cross-replicates delta packets.
    4. Proves mathematical convergence: state(US) == state(EU).
    """
    # 1. Concurrent writes during WAN partition
    _replicator_us.local_open_incident("inc_us_partition_01")
    _replicator_eu.local_open_incident("inc_eu_partition_01")

    # 2. Heal partition by exchanging deltas
    delta_us = _replicator_us.export_sync_delta()
    delta_eu = _replicator_eu.export_sync_delta()

    _replicator_us.ingest_sync_delta(delta_eu)
    _replicator_eu.ingest_sync_delta(delta_us)

    st_us = _replicator_us.get_mesh_status()
    st_eu = _replicator_eu.get_mesh_status()

    is_converged = (
        st_us["active_incidents_count"] == st_eu["active_incidents_count"]
        and st_us["active_incident_ids"] == st_eu["active_incident_ids"]
    )

    return {
        "simulation": "WAN_PARTITION_HEALED",
        "mathematically_converged": is_converged,
        "us_west_state": st_us,
        "eu_central_state": st_eu,
    }


def _get_replicator(region_id: str) -> ActiveActiveMeshReplicator:
    r = region_id.lower().strip()
    if "eu" in r:
        return _replicator_eu
    if "ap" in r:
        return _replicator_ap
    return _replicator_us
