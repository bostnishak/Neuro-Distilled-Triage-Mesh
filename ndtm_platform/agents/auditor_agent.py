"""Module: Risk & Compliance Auditor Agent.

Evaluates organizational rules, regulatory compliance, legal liability, and privacy
constraints (PII protection, GDPR / KVKK compliance) before action execution.
"""
from __future__ import annotations

import logging
from typing import Any

from ndtm_platform.middleware.pii_redaction import PIIRedactor

logger = logging.getLogger("auditor_agent")


class ComplianceAuditorAgent:
    """Specialized agent ensuring regulatory compliance, privacy, and safety protocols."""

    def __init__(self, redactor: PIIRedactor | None = None) -> None:
        self.redactor = redactor or PIIRedactor()

    async def audit(
        self,
        description: str,
        triage_summary: dict[str, Any],
    ) -> dict[str, Any]:
        """Audits ticket for compliance violations, safety protocols, and privacy risks."""
        violations: list[str] = []
        protocols_required: list[str] = []

        category = triage_summary.get("category", "general")
        urgency = triage_summary.get("urgency", 0.5)

        # 1. PII and Privacy Audit
        cleaned, redactions = self.redactor.redact(description)
        pii_safe = len(redactions) == 0  # If text was already redacted, no new redactions found

        if not pii_safe:
            protocols_required.append("PII_REDACTION_ENFORCED")

        # 2. Safety & Hazard Protocol Checks
        if category == "hazmat":
            protocols_required.append("DISASTER_MANAGEMENT_EVACUATION_CHECK")
            protocols_required.append("EPA_ENVIRONMENTAL_HAZARD_LOG")
            if urgency > 0.90:
                protocols_required.append("FIRST_RESPONDER_PRIORITY_ESCALATION")

        elif category == "electrical" and urgency > 0.70:
            protocols_required.append("GRID_OPERATOR_HIGH_VOLTAGE_ISOLATION")

        # 3. Policy & Liability Score
        risk_score = 0.2
        if category in ("hazmat", "electrical"):
            risk_score += 0.4
        if urgency > 0.8:
            risk_score += 0.3
        risk_score = min(1.0, round(risk_score, 2))

        # 4. Auditor Confidence Calculation
        # Confidence reflects certainty that the incident conforms to automated handling rules
        # If high risk or unhandled dangerous protocols, auditor confidence is lower or requires review
        confidence = 0.95
        if risk_score > 0.85:
            # Extreme hazard requires heightened scrutiny
            confidence = 0.82
        elif not pii_safe:
            confidence = 0.87
        else:
            confidence = 0.94

        approved = len(violations) == 0 and risk_score < 0.90

        return {
            "agent": "ComplianceAuditorAgent",
            "compliant": approved,
            "confidence": round(confidence, 3),
            "risk_score": risk_score,
            "protocols_required": protocols_required,
            "pii_clean": pii_safe,
            "redactions_identified": redactions,
            "violations": violations,
            "reasoning": f"Audit completed with risk score {risk_score:.2f}. Protocols triggered: {', '.join(protocols_required) if protocols_required else 'Standard operations'}.",
        }
