"""Module: Multi-Agent Workflow State Machine & Human-in-the-Loop Orchestrator.

Orchestrates the collaborative lifecycle:
1. State: TriageSpecialistAgent (Categorization & Historical Context)
2. State: ComplianceAuditorAgent (Regulatory, Safety & PII Audit)
3. State: Consensus Check (Threshold = 0.85)
   * If consensus < 0.85: Suspend workflow, persist state to PostgreSQL `hitl_review_tasks`,
     and emit an async review event to RabbitMQ.
   * If consensus >= 0.85: State -> ActionExecutionAgent (MCP Tool Dispatch).
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from uuid import UUID, uuid4

import asyncpg

from ndtm_platform.agents.auditor_agent import ComplianceAuditorAgent
from ndtm_platform.agents.execution_agent import ActionExecutionAgent
from ndtm_platform.agents.triage_agent import TriageSpecialistAgent
from ndtm_platform.models.schemas import MultiAgentWorkflowRequest, MultiAgentWorkflowResponse

logger = logging.getLogger("state_machine")

CONSENSUS_THRESHOLD = 0.85


class MultiAgentStateMachine:
    """Stateful orchestrator for multi-agent triage, compliance, and MCP tool execution."""

    def __init__(
        self,
        pool: asyncpg.Pool,
        triage_agent: TriageSpecialistAgent | None = None,
        auditor_agent: ComplianceAuditorAgent | None = None,
        execution_agent: ActionExecutionAgent | None = None,
        rabbitmq_channel: Any = None,
        consensus_threshold: float = CONSENSUS_THRESHOLD,
    ) -> None:
        self.pool = pool
        self.triage_agent = triage_agent or TriageSpecialistAgent(pool)
        self.auditor_agent = auditor_agent or ComplianceAuditorAgent()
        self.execution_agent = execution_agent or ActionExecutionAgent()
        self.rabbitmq_channel = rabbitmq_channel
        self.consensus_threshold = consensus_threshold

    def calculate_consensus(
        self,
        triage_confidence: float,
        auditor_confidence: float,
        is_compliant: bool,
    ) -> float:
        """Calculates multi-agent consensus confidence score [0.0, 1.0]."""
        # Weighted aggregate: 45% auditor, 40% triage, 15% compliance bonus
        compliance_weight = 0.15 if is_compliant else 0.0
        score = (triage_confidence * 0.40) + (auditor_confidence * 0.45) + compliance_weight
        return round(min(1.0, max(0.0, score)), 3)

    async def run_workflow(self, request: MultiAgentWorkflowRequest) -> MultiAgentWorkflowResponse:
        """Executes the multi-agent graph with automated suspension for HITL."""
        ticket_id = request.ticket_id
        description = request.description

        # Node 1: Triage & Domain Specialist Agent
        triage_res = await self.triage_agent.analyze(
            description=description,
            category_hint=request.category,
            ticket_id=ticket_id,
        )
        triage_conf = triage_res.get("confidence", 0.80)

        # Node 2: Risk & Compliance Auditor Agent
        audit_res = await self.auditor_agent.audit(
            description=description,
            triage_summary=triage_res,
        )
        auditor_conf = audit_res.get("confidence", 0.80)
        is_compliant = audit_res.get("compliant", True)

        # Consensus Gate
        consensus_score = self.calculate_consensus(triage_conf, auditor_conf, is_compliant)
        logger.info("Multi-agent consensus calculated: %.3f (Threshold: %.2f)", consensus_score, self.consensus_threshold)

        # Human-in-the-Loop check
        if consensus_score < self.consensus_threshold:
            logger.warning(
                "Consensus score %.3f below threshold %.2f! Suspending workflow for Human-in-the-Loop review.",
                consensus_score,
                self.consensus_threshold,
            )

            # Persist state to hitl_review_tasks
            task_id = uuid4()
            state_snapshot = {
                "description": description,
                "triage_summary": triage_res,
                "compliance_audit": audit_res,
                "consensus_score": consensus_score,
            }

            async with self.pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO hitl_review_tasks (
                        id, ticket_id, agent_name, consensus_score, workflow_state, status
                    ) VALUES ($1, $2, $3, $4, $5::jsonb, 'pending_review');
                    """,
                    task_id,
                    ticket_id,
                    "MultiAgentConsensusEngine",
                    consensus_score,
                    json.dumps(state_snapshot),
                )

            # Emit async event to RabbitMQ
            await self._emit_hitl_event(task_id, ticket_id, consensus_score, state_snapshot)

            return MultiAgentWorkflowResponse(
                ticket_id=ticket_id,
                consensus_reached=False,
                consensus_score=consensus_score,
                triage_summary=triage_res,
                compliance_audit=audit_res,
                execution_plan={"status": "suspended", "reason": "Awaiting supervisor human approval"},
                hitl_required=True,
                review_task_id=task_id,
            )

        # Node 3: Action Execution Agent (runs only when consensus >= 0.85)
        execution_res = await self.execution_agent.execute_plan(
            ticket_id=ticket_id,
            description=description,
            triage_summary=triage_res,
            audit_summary=audit_res,
        )

        return MultiAgentWorkflowResponse(
            ticket_id=ticket_id,
            consensus_reached=True,
            consensus_score=consensus_score,
            triage_summary=triage_res,
            compliance_audit=audit_res,
            execution_plan=execution_res,
            hitl_required=False,
            review_task_id=None,
        )

    async def _emit_hitl_event(
        self,
        task_id: UUID,
        ticket_id: UUID | None,
        consensus_score: float,
        state: dict[str, Any],
    ) -> None:
        """Publishes pending human review notification to RabbitMQ."""
        if not self.rabbitmq_channel:
            return
        try:
            import aio_pika
            payload = json.dumps({
                "event": "hitl_approval_required",
                "task_id": str(task_id),
                "ticket_id": str(ticket_id) if ticket_id else None,
                "consensus_score": consensus_score,
                "reason": "Agentic consensus below 0.85 threshold",
            }).encode("utf-8")

            await self.rabbitmq_channel.default_exchange.publish(
                aio_pika.Message(body=payload, content_type="application/json"),
                routing_key="hitl_queue",
            )
            logger.info("Published HITL task %s to RabbitMQ hitl_queue", task_id)
        except Exception as exc:
            logger.warning("RabbitMQ HITL event publish failed: %s", exc)
