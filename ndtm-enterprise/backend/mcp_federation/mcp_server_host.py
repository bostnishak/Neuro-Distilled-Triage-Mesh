"""Model Context Protocol (MCP) Server Host.
Exposes sandboxed tools to autonomous agents over JSON-RPC 2.0.
"""
from __future__ import annotations

import time
from typing import Any
from uuid import uuid4

from backend.causal_twin.counterfactual_engine import CounterfactualEngine
from backend.causal_twin.topology_graph import ISTANBUL_INFRASTRUCTURE_NODES
from backend.mcp_federation.protocol_schemas import (
    CallToolRequest,
    ListToolsResult,
    ToolCallResult,
    ToolDefinition,
)

REGISTERED_TOOLS: list[ToolDefinition] = [
    ToolDefinition(
        name="query_infra_telemetry",
        description="Query live health, voltage, and telemetry for an infrastructure node.",
        inputSchema={
            "type": "object",
            "properties": {
                "node_code": {"type": "string", "description": "Canonical node identifier"}
            },
            "required": ["node_code"],
        },
    ),
    ToolDefinition(
        name="execute_counterfactual",
        description="Run Pearl's do-calculus counterfactual intervention on the causal digital twin.",
        inputSchema={
            "type": "object",
            "properties": {
                "failed_node_code": {"type": "string"},
                "intervened_node_code": {"type": "string"},
            },
            "required": ["failed_node_code", "intervened_node_code"],
        },
    ),
    ToolDefinition(
        name="propose_contingency_plan",
        description="Generate an SMT-compliant contingency dispatch and rerouting plan.",
        inputSchema={
            "type": "object",
            "properties": {
                "incident_id": {"type": "string"},
                "risk_tier": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH", "CRITICAL"]},
            },
            "required": ["incident_id", "risk_tier"],
        },
    ),
]


class MCPServerHost:
    """Hosts MCP tool execution pipeline with sandboxing and telemetry."""

    def __init__(self) -> None:
        self.counterfactual = CounterfactualEngine()

    def list_tools(self) -> ListToolsResult:
        return ListToolsResult(tools=REGISTERED_TOOLS)

    async def execute_tool(self, request: CallToolRequest) -> ToolCallResult:
        tool_name = request.name
        args = request.arguments

        if tool_name == "query_infra_telemetry":
            node_code = args.get("node_code", "")
            match = next((n for n in ISTANBUL_INFRASTRUCTURE_NODES if n.node_code == node_code), None)
            if not match:
                return ToolCallResult(
                    content=[{"type": "text", "text": f"Node {node_code} not found in topology."}],
                    isError=True,
                )
            return ToolCallResult(
                content=[{
                    "type": "json",
                    "data": {
                        "node_code": match.node_code,
                        "node_type": match.node_type,
                        "health_score": match.current_health_score,
                        "capacity_kw": match.capacity_kw,
                        "metadata": match.metadata,
                    },
                }],
                isError=False,
            )

        if tool_name == "execute_counterfactual":
            failed = args.get("failed_node_code", "SUBSTATION_IKITELLI")
            intervened = args.get("intervened_node_code", "FIBER_BOGAZICI_NORTH")
            res = self.counterfactual.evaluate_intervention(failed, intervened)
            return ToolCallResult(
                content=[{"type": "json", "data": res}],
                isError=False,
            )

        if tool_name == "propose_contingency_plan":
            inc_id = args.get("incident_id", str(uuid4()))
            tier = args.get("risk_tier", "HIGH")
            plan = {
                "incident_id": inc_id,
                "risk_tier": tier,
                "action": "AUTOMATED_REROUTING_DISPATCH",
                "teams_allocated": ["TEAM_ALPHA_FIBER", "TEAM_BETA_HV"],
                "mitigation_minutes": 35,
                "requires_hitl": tier in ("HIGH", "CRITICAL"),
            }
            return ToolCallResult(
                content=[{"type": "json", "data": plan}],
                isError=False,
            )

        return ToolCallResult(
            content=[{"type": "text", "text": f"Unknown tool: {tool_name}"}],
            isError=True,
        )


mcp_server = MCPServerHost()
