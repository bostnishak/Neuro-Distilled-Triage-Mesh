"""Unit tests for Multi-Agent Workflow State Machine and Consensus HITL."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from ndtm_platform.agents.auditor_agent import ComplianceAuditorAgent
from ndtm_platform.agents.execution_agent import ActionExecutionAgent
from ndtm_platform.agents.state_machine import MultiAgentStateMachine
from ndtm_platform.agents.triage_agent import TriageSpecialistAgent
from ndtm_platform.models.schemas import MultiAgentWorkflowRequest


@pytest.mark.asyncio
async def test_triage_and_auditor_agent_analysis():
    # Mock pool for triage agent
    mock_pool = MagicMock()
    mock_conn = AsyncMock()
    mock_conn.fetch.return_value = []
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

    triage_agent = TriageSpecialistAgent(pool=mock_pool)
    res = await triage_agent.analyze("Ana caddede büyük bir su borusu patladı ve caddeyi su bastı.")

    assert res["category"] == "plumbing"
    assert res["confidence"] >= 0.85
    assert res["urgency"] >= 0.70

    auditor_agent = ComplianceAuditorAgent()
    audit_res = await auditor_agent.audit(
        description="Ana caddede büyük bir su borusu patladı",
        triage_summary=res,
    )
    assert audit_res["compliant"] is True
    assert audit_res["confidence"] >= 0.85


@pytest.mark.asyncio
async def test_execution_agent_mcp_tools():
    exec_agent = ActionExecutionAgent()
    triage_summary = {"category": "electrical", "urgency": 0.85}
    audit_summary = {"compliant": True, "protocols_required": ["GRID_OPERATOR_HIGH_VOLTAGE_ISOLATION"]}

    plan = await exec_agent.execute_plan(
        ticket_id=None,
        description="Trafo patladı ve yangın çıktı",
        triage_summary=triage_summary,
        audit_summary=audit_summary,
    )

    assert plan["confidence"] >= 0.90
    assert plan["actions_executed_count"] >= 1
    tool_names = [call["tool"] for call in plan["tool_calls"]]
    assert "dispatch_technician_crew" in tool_names


@pytest.mark.asyncio
async def test_state_machine_hitl_suspension_on_low_consensus():
    mock_pool = MagicMock()
    mock_conn = AsyncMock()
    mock_conn.execute.return_value = None
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

    # Setup low confidence scenario
    mock_triage = MagicMock()
    mock_triage.analyze = AsyncMock(return_value={"category": "general", "confidence": 0.60, "urgency": 0.3})

    mock_auditor = MagicMock()
    mock_auditor.audit = AsyncMock(return_value={"compliant": False, "confidence": 0.50, "risk_score": 0.95})

    state_machine = MultiAgentStateMachine(
        pool=mock_pool,
        triage_agent=mock_triage,
        auditor_agent=mock_auditor,
        execution_agent=ActionExecutionAgent(),
        consensus_threshold=0.85,
    )

    req = MultiAgentWorkflowRequest(description="Garip bir ses var.")
    resp = await state_machine.run_workflow(req)

    # Must be suspended for Human-in-the-Loop review!
    assert resp.consensus_reached is False
    assert resp.hitl_required is True
    assert resp.consensus_score < 0.85
    assert resp.review_task_id is not None
    assert resp.execution_plan["status"] == "suspended"
