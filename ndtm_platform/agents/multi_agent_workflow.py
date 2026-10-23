"""Module: Multi-Agent Workflow State Machine Compatibility Layer.

Re-exports MultiAgentStateMachine and agents for modular imports.
"""
from __future__ import annotations

from ndtm_platform.agents.auditor_agent import ComplianceAuditorAgent
from ndtm_platform.agents.execution_agent import ActionExecutionAgent
from ndtm_platform.agents.state_machine import CONSENSUS_THRESHOLD, MultiAgentStateMachine
from ndtm_platform.agents.triage_agent import TriageSpecialistAgent

__all__ = [
    "MultiAgentStateMachine",
    "TriageSpecialistAgent",
    "ComplianceAuditorAgent",
    "ActionExecutionAgent",
    "CONSENSUS_THRESHOLD",
]
