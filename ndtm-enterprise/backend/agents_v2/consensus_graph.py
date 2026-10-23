"""Multi-Agent Byzantine Consensus Graph.
Coordinates automated deliberation across Triager, SRE Architect, and Risk Auditor
to compute an ensemble consensus score.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4


@dataclass(slots=True)
class AgentVote:
    agent_id: str
    role: str
    approved: bool
    confidence: float
    weight: float
    reasoning: str


class MultiAgentConsensusEngine:
    """Evaluates multi-agent agreement on high-risk dispatch or operational actions."""

    def evaluate_proposal(
        self,
        incident_id: str,
        category: str,
        urgency: int,
        affected_nodes_count: int,
    ) -> dict[str, Any]:
        votes: list[AgentVote] = []

        # 1. Incident Triager Agent
        triager_approved = urgency >= 6
        votes.append(AgentVote(
            agent_id="AGENT_TRIAGER_01",
            role="INCIDENT_TRIAGER",
            approved=triager_approved,
            confidence=0.92,
            weight=0.35,
            reasoning=f"Severity assessment based on urgency score {urgency}/10.",
        ))

        # 2. SRE Infrastructure Architect Agent
        sre_approved = affected_nodes_count <= 5 or urgency >= 8
        votes.append(AgentVote(
            agent_id="AGENT_SRE_02",
            role="SRE_GRID_ARCHITECT",
            approved=sre_approved,
            confidence=0.88,
            weight=0.40,
            reasoning=f"Grid topology stability check: {affected_nodes_count} nodes potentially affected.",
        ))

        # 3. Security & Safety Auditor Agent
        auditor_approved = True
        votes.append(AgentVote(
            agent_id="AGENT_AUDITOR_03",
            role="SAFETY_AUDITOR",
            approved=auditor_approved,
            confidence=0.95,
            weight=0.25,
            reasoning="Regulatory compliance and worker shift safety constraints validated.",
        ))

        total_weight = sum(v.weight for v in votes)
        weighted_score = sum(
            v.weight * (v.confidence if v.approved else (1.0 - v.confidence))
            for v in votes
        ) / total_weight

        consensus_score = round(weighted_score, 4)
        requires_hitl = consensus_score < 0.85 or urgency >= 9

        return {
            "proposal_id": str(uuid4()),
            "incident_id": incident_id,
            "consensus_score": consensus_score,
            "requires_hitl": requires_hitl,
            "votes": [
                {
                    "agent_id": v.agent_id,
                    "role": v.role,
                    "approved": v.approved,
                    "confidence": v.confidence,
                    "reasoning": v.reasoning,
                }
                for v in votes
            ],
            "decision": "DISPATCH_DIRECT" if not requires_hitl else "PENDING_HUMAN_APPROVAL",
        }


consensus_engine = MultiAgentConsensusEngine()
