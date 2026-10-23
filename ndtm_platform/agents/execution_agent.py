"""Module: Action Execution Agent with Model Context Protocol (MCP) Tools.

Formulates resolution plans and executes external integrations using standard
Model Context Protocol (MCP) tool schemas and JSON-RPC dispatchers.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

logger = logging.getLogger("execution_agent")


# =============================================================================
# MCP Tool Registry & Schema Definitions
# =============================================================================
MCP_TOOLS_SPEC = [
    {
        "name": "dispatch_technician_crew",
        "description": "Dispatches an on-call municipal repair crew matching required skill and priority.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "skill": {"type": "string", "enum": ["electrical", "plumbing", "pavement", "hazmat", "general"]},
                "priority": {"type": "integer", "minimum": 1, "maximum": 4},
                "notes": {"type": "string"},
            },
            "required": ["skill", "priority"],
        },
    },
    {
        "name": "notify_emergency_services",
        "description": "Alerts fire, hazmat, or medical first responders for life-safety incidents.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "service": {"type": "string", "enum": ["fire_hazmat", "police", "medical"]},
                "severity": {"type": "string", "enum": ["critical", "high"]},
                "incident_summary": {"type": "string"},
            },
            "required": ["service", "severity", "incident_summary"],
        },
    },
    {
        "name": "update_public_works_crm",
        "description": "Updates the central civic incident record with workflow metadata and SLA timer.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ticket_id": {"type": "string"},
                "status": {"type": "string"},
                "assigned_department": {"type": "string"},
            },
            "required": ["ticket_id", "status"],
        },
    },
]


class ActionExecutionAgent:
    """Specialized agent responsible for formulating execution plans and triggering MCP tools."""

    def __init__(self) -> None:
        self.available_tools = {tool["name"]: tool for tool in MCP_TOOLS_SPEC}

    async def execute_plan(
        self,
        ticket_id: UUID | None,
        description: str,
        triage_summary: dict[str, Any],
        audit_summary: dict[str, Any],
    ) -> dict[str, Any]:
        """Formulates response and determines necessary MCP tool invocations."""
        category = triage_summary.get("category", "general")
        urgency = triage_summary.get("urgency", 0.5)
        protocols = audit_summary.get("protocols_required", [])

        tool_calls: list[dict[str, Any]] = []

        # 1. Determine tool calls based on domain and safety protocols
        if "FIRST_RESPONDER_PRIORITY_ESCALATION" in protocols or (category == "hazmat" and urgency > 0.85):
            tool_calls.append({
                "tool": "notify_emergency_services",
                "parameters": {
                    "service": "fire_hazmat",
                    "severity": "critical",
                    "incident_summary": f"Urgent hazmat incident flagged: {description[:100]}",
                },
                "status": "executed_mock",
            })

        # 2. Field technician dispatch
        skill_map = {
            "plumbing": "plumbing",
            "electrical": "electrical",
            "pavement": "pavement",
            "hazmat": "hazmat",
            "general": "general",
        }
        skill = skill_map.get(category, "general")
        priority = 1 if urgency > 0.8 else (2 if urgency > 0.6 else 3)

        tool_calls.append({
            "tool": "dispatch_technician_crew",
            "parameters": {
                "skill": skill,
                "priority": priority,
                "notes": f"Automated crew dispatch for ticket {ticket_id or 'new'}.",
            },
            "status": "executed_mock",
        })

        # 3. CRM sync
        if ticket_id:
            tool_calls.append({
                "tool": "update_public_works_crm",
                "parameters": {
                    "ticket_id": str(ticket_id),
                    "status": "processing",
                    "assigned_department": f"dept_{category}",
                },
                "status": "executed_mock",
            })

        # Calculate execution confidence
        confidence = 0.95
        if not audit_summary.get("compliant", False):
            confidence = 0.70  # Low confidence if compliance not approved

        action_summary = (
            f"Action plan formulated with {len(tool_calls)} MCP actions: "
            + ", ".join(call["tool"] for call in tool_calls)
        )

        return {
            "agent": "ActionExecutionAgent",
            "confidence": round(confidence, 3),
            "tool_calls": tool_calls,
            "actions_executed_count": len(tool_calls),
            "summary": action_summary,
            "mcp_tools_available": list(self.available_tools.keys()),
        }
