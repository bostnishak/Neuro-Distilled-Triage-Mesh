import datetime
import json
import uuid
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field

from core.security_ed25519_jwt import global_signer
from domain.value_objects import MerkleHash


class DomainEvent(BaseModel):
    """Immutable event stored in append-only kernel_domain_events ledger."""
    model_config = ConfigDict(strict=True, frozen=True)

    event_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    aggregate_type: str
    aggregate_id: uuid.UUID
    event_type: str
    version: int = 1
    payload: Dict[str, Any]
    occurred_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    correlation_id: Optional[str] = None
    signature_hex: Optional[str] = None

    def canonical_bytes(self) -> bytes:
        """Serializes event to deterministic canonical JSON byte array for cryptographic signing."""
        canonical_dict = {
            "event_id": str(self.event_id),
            "aggregate_type": self.aggregate_type,
            "aggregate_id": str(self.aggregate_id),
            "event_type": self.event_type,
            "version": self.version,
            "payload": self.payload,
            "occurred_at": self.occurred_at.isoformat(),
            "correlation_id": self.correlation_id,
        }
        return json.dumps(canonical_dict, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def compute_hash(self) -> MerkleHash:
        """Computes SHA-256 hash of event bytes."""
        return MerkleHash.compute(self.canonical_bytes())

    def sign(self) -> "DomainEvent":
        """Signs the canonical event bytes with kernel Ed25519 key and returns updated event."""
        sig = global_signer.sign_hex(self.canonical_bytes())
        return self.model_copy(update={"signature_hex": sig})

    def verify_signature(self) -> bool:
        """Verifies Ed25519 signature against kernel public key."""
        if not self.signature_hex:
            return False
        return global_signer.verify_hex(self.signature_hex, self.canonical_bytes())


class IncidentIngestedEvent(DomainEvent):
    """Fired when raw incident report is scrubbed, classified, and persisted."""
    pass


class HawkesClusterFormedEvent(DomainEvent):
    """Fired when an incident excites or forms an aftershock spatial-temporal cluster."""
    pass


class ModelTriageDispatchedEvent(DomainEvent):
    """Fired when student or teacher model produces triage inference and confidence."""
    pass


class SpeculativeDraftRejectedEvent(DomainEvent):
    """Fired when small model draft output fails teacher verification threshold."""
    pass


class SmtDispatchOptimizedEvent(DomainEvent):
    """Fired when Z3 MaxSMT solver computes verified Pareto-optimal dispatch assignment."""
    pass


class HitlApprovalRequiredEvent(DomainEvent):
    """Fired when high-risk or low-confidence incident requires human arbiter sign-off."""
    pass


class HitlDecisionRecordedEvent(DomainEvent):
    """Fired when human arbiter commits cryptographic approval or rejection."""
    pass


class MerkleBlockSealedEvent(DomainEvent):
    """Fired when audit ledger seals a batch of events into an immutable block."""
    pass


class ByzantineNodePrunedEvent(DomainEvent):
    """Fired when federated worker submission is discarded via Multi-Krum filter."""
    pass
