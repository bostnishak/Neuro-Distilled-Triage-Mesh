import datetime
import uuid
import pytest
from domain.services.merkle_audit_ledger import MerkleAuditLedger
from domain.services.time_travel_flight_recorder import TimeTravelFlightRecorder
from domain.events import IncidentIngestedEvent, DomainEvent
from domain.value_objects import MerkleHash
from core.exceptions import MerkleTamperDetectedException


def test_merkle_tree_and_block_sealing():
    ev1 = IncidentIngestedEvent(
        aggregate_type="Incident",
        aggregate_id=uuid.uuid4(),
        event_type="IncidentIngested",
        payload={"title": "Test Incident 1", "urgency": "HIGH"},
    ).sign()

    ev2 = IncidentIngestedEvent(
        aggregate_type="Incident",
        aggregate_id=uuid.uuid4(),
        event_type="IncidentIngested",
        payload={"title": "Test Incident 2", "urgency": "CRITICAL"},
    ).sign()

    parent_hash = "0" * 64
    block_hash, root, sig, sealed_at = MerkleAuditLedger.seal_block(
        height=1,
        parent_hash=parent_hash,
        events=[ev1, ev2],
    )

    assert len(block_hash.digest) == 64
    assert len(root.digest) == 64
    assert len(sig) == 128

    # Verify link
    is_valid = MerkleAuditLedger.verify_chain_link(
        prev_block_hash=parent_hash,
        current_parent_hash=parent_hash,
        current_block_hash=block_hash.digest,
        merkle_root=root.digest,
        height=1,
        timestamp_iso=sealed_at.isoformat(),
        events_count=2,
        signature_hex=sig,
    )
    assert is_valid is True

    # Tampered block hash must raise exception
    with pytest.raises(MerkleTamperDetectedException):
        MerkleAuditLedger.verify_chain_link(
            prev_block_hash=parent_hash,
            current_parent_hash=parent_hash,
            current_block_hash="f" * 64,
            merkle_root=root.digest,
            height=1,
            timestamp_iso=sealed_at.isoformat(),
            events_count=2,
            signature_hex=sig,
        )


def test_time_travel_event_sourcing_projection():
    recorder = TimeTravelFlightRecorder()
    inc_id = uuid.uuid4()
    t0 = datetime.datetime(2026, 10, 19, 10, 0, 0, tzinfo=datetime.timezone.utc)
    t1 = datetime.datetime(2026, 10, 19, 10, 5, 0, tzinfo=datetime.timezone.utc)
    t2 = datetime.datetime(2026, 10, 19, 10, 10, 0, tzinfo=datetime.timezone.utc)

    ev1 = DomainEvent(
        aggregate_type="Incident",
        aggregate_id=inc_id,
        event_type="IncidentIngested",
        occurred_at=t0,
        payload={"title": "Water Pipe Burst", "urgency": "MEDIUM", "latitude": 41.0, "longitude": 28.9},
    )

    ev2 = DomainEvent(
        aggregate_type="Incident",
        aggregate_id=inc_id,
        event_type="ModelTriageDispatched",
        occurred_at=t1,
        payload={"decision": "WATER_MAINS", "confidence": 0.94},
    )

    events = [ev1, ev2]

    # Reconstruct state as of t0 (only ev1 applied)
    snap_t0 = recorder.project_state_as_of(events, as_of_time=t0)
    assert snap_t0["applied_events_count"] == 1
    assert snap_t0["incidents"][str(inc_id)]["triage_state"] == "INGESTED"

    # Reconstruct state as of t2 (both ev1 and ev2 applied)
    snap_t2 = recorder.project_state_as_of(events, as_of_time=t2)
    assert snap_t2["applied_events_count"] == 2
    assert snap_t2["incidents"][str(inc_id)]["triage_state"] == "TRIAGED"
    assert snap_t2["incidents"][str(inc_id)]["decision"] == "WATER_MAINS"
