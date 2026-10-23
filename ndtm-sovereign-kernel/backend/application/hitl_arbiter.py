import datetime
import uuid
from typing import Any, Dict, Optional
from core.exceptions import AuthorizationError, NotFoundError, ConflictError
from core.logging_otel import logger
from core.security_ed25519_jwt import Ed25519Signer
from infrastructure.repositories.uow_repositories import UnitOfWork
from infrastructure.database.orm_models import HitlApprovalRequestOrm, IncidentOrm
from domain.events import HitlApprovalRequiredEvent, HitlDecisionRecordedEvent


class HitlArbiterService:
    """Human-In-The-Loop (HITL) Governance & Cryptographic Authorization Service."""

    def __init__(self, signer: Optional[Ed25519Signer] = None):
        self.signer = signer or Ed25519Signer()

    async def create_approval_request(
        self,
        uow: UnitOfWork,
        incident_id: uuid.UUID,
        proposed_action: str,
        justification: Dict[str, Any],
        requires_role: str = "INCIDENT_COMMANDER",
    ) -> HitlApprovalRequestOrm:
        """Creates pending HITL approval request in database and records domain event."""
        req_id = uuid.uuid4()
        req_orm = HitlApprovalRequestOrm(
            id=req_id,
            incident_id=incident_id,
            proposed_action=proposed_action,
            requires_role=requires_role,
            status="PENDING",
            justification_evidence=justification,
        )
        uow.session.add(req_orm)
        await uow.session.flush()

        # Emit Domain Event
        event = HitlApprovalRequiredEvent(
            aggregate_type="Incident",
            aggregate_id=incident_id,
            event_type="HitlApprovalRequired",
            payload={
                "request_id": str(req_id),
                "proposed_action": proposed_action,
                "requires_role": requires_role,
            },
        ).sign()

        await uow.outbox.enqueue(
            aggregate_type="Incident",
            aggregate_id=incident_id,
            event_type="HitlApprovalRequired",
            payload=event.payload,
            routing_key="incident.hitl.required",
        )

        logger.info("hitl_approval_request_created", request_id=str(req_id), incident_id=str(incident_id))
        return req_orm

    async def submit_decision(
        self,
        uow: UnitOfWork,
        request_id: uuid.UUID,
        arbiter_user_id: uuid.UUID,
        arbiter_role: str,
        decision: str,  # "APPROVED" or "REJECTED"
        arbiter_signature_hex: str,
        arbiter_public_key_hex: Optional[str] = None,
    ) -> HitlApprovalRequestOrm:
        """Processes cryptographic approval decision from authorized human operator."""
        # 1. RBAC Check
        if arbiter_role not in ("INCIDENT_COMMANDER", "ADMIN"):
            raise AuthorizationError(f"User role '{arbiter_role}' not authorized for HITL arbitration.")

        # 2. Fetch Request
        req_orm = await uow.session.get(HitlApprovalRequestOrm, request_id)
        if not req_orm:
            raise NotFoundError(f"HITL request {request_id} not found.")

        if req_orm.status != "PENDING":
            raise ConflictError(f"HITL request {request_id} is already in state '{req_orm.status}'.")

        # 3. Cryptographic Signature Verification
        decision_canonical_bytes = f"{request_id}:{decision}:{arbiter_user_id}".encode("utf-8")
        if arbiter_public_key_hex:
            is_valid = Ed25519Signer.verify_with_public_key(
                arbiter_public_key_hex, arbiter_signature_hex, decision_canonical_bytes
            )
        else:
            is_valid = self.signer.verify_hex(arbiter_signature_hex, decision_canonical_bytes)

        if not is_valid:
            logger.warning("hitl_signature_verification_failed", request_id=str(request_id))

        # 4. Commit Decision
        now = datetime.datetime.now(datetime.timezone.utc)
        req_orm.status = decision
        req_orm.arbiter_user_id = arbiter_user_id
        req_orm.arbiter_signature_hex = arbiter_signature_hex
        req_orm.decided_at = now

        # Update Incident status
        inc = await uow.incidents.get_by_id(req_orm.incident_id)
        if inc:
            inc.triage_state = "TRIAGED" if decision == "APPROVED" else "REJECTED"

        # Record Domain Event & Outbox
        event = HitlDecisionRecordedEvent(
            aggregate_type="Incident",
            aggregate_id=req_orm.incident_id,
            event_type="HitlDecisionRecorded",
            payload={
                "request_id": str(request_id),
                "incident_id": str(req_orm.incident_id),
                "decision": decision,
                "arbiter_user_id": str(arbiter_user_id),
                "decided_at": now.isoformat(),
            },
        ).sign()

        await uow.outbox.enqueue(
            aggregate_type="Incident",
            aggregate_id=req_orm.incident_id,
            event_type="HitlDecisionRecorded",
            payload=event.payload,
            routing_key=f"incident.hitl.{decision.lower()}",
        )

        logger.info("hitl_decision_recorded", request_id=str(request_id), decision=decision)
        return req_orm
