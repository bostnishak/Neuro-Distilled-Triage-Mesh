"""Model Context Protocol (MCP) JSON-RPC 2.0 schemas and tool specs."""
from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class ToolDefinition(BaseModel):
    name: str
    description: str
    inputSchema: dict[str, Any]


class ListToolsResult(BaseModel):
    tools: list[ToolDefinition]


class CallToolRequest(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolCallResult(BaseModel):
    content: list[dict[str, Any]]
    isError: bool = False
