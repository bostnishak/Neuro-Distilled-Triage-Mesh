"""Model Context Protocol (MCP) & Byzantine Human-In-The-Loop (HITL) Router (NDTM v2.0)."""
from __future__ import annotations

import logging
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status

from backend.api.deps import require_role
from backend.agents_v2.hitl_crypto_gate import hitl_crypto_gate
from backend.db.models import User
from backend.mcp_federation.mcp_server_host import mcp_server
from backend.mcp_federation.protocol_schemas import CallToolRequest
from backend.schemas.auth import UserRole
from backend.schemas.v2_schemas import (
    HITLApprovalItem,
    HITLSignRequest,
    HITLSignResponse,
    JsonRpcRequest,
    JsonRpcResponse,
)

logger = logging.getLogger("api.mcp_and_hitl")
router = APIRouter(prefix="", tags=["MCP & HITL Sovereign Consensus"])


@router.post("/mcp/rpc", response_model=JsonRpcResponse)
async def handle_mcp_jsonrpc_request(req: JsonRpcRequest) -> JsonRpcResponse:
    """JSON-RPC 2.0 endpoint dispatching Model Context Protocol (MCP) commands."""
    if req.method == "tools/list":
        tools_res = mcp_server.list_tools()
        return JsonRpcResponse(
            jsonrpc="2.0",
            result=tools_res.model_dump(),
            id=req.id,
        )

    elif req.method == "tools/call":
        params = req.params or {}
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        if not tool_name:
            return JsonRpcResponse(
                jsonrpc="2.0",
                error={"code": -32602, "message": "Missing 'name' in tools/call params."},
                id=req.id,
            )

        call_req = CallToolRequest(name=tool_name, arguments=arguments)
        call_res = await mcp_server.execute_tool(call_req)
        return JsonRpcResponse(
            jsonrpc="2.0",
            result=call_res.model_dump(),
            id=req.id,
        )

    return JsonRpcResponse(
        jsonrpc="2.0",
        error={"code": -32601, "message": f"Method '{req.method}' not found."},
        id=req.id,
    )


@router.get("/mcp/tools")
async def list_mcp_tools() -> dict[str, Any]:
    """Convenience REST endpoint for MCP tool discovery."""
    res = mcp_server.list_tools()
    return {"tools": [t.model_dump() for t in res.tools]}


@router.get("/hitl/pending", response_model=list[HITLApprovalItem])
async def list_pending_hitl_requests() -> list[HITLApprovalItem]:
    """Retrieves all high-risk actions awaiting cryptographic Ed25519 human authorization."""
    items = hitl_crypto_gate.list_pending()
    return [
        HITLApprovalItem(
            id=item["id"],
            incident_id=item.get("incident_id"),
            proposed_action=item["proposed_action"],
            agent_consensus_score=item["agent_consensus_score"],
            z3_proof_hash=item["z3_proof_hash"],
            status=item["status"],
            created_at=item["created_at"],
        )
        for item in items
    ]


@router.post("/hitl/{request_id}/sign", response_model=HITLSignResponse)
async def sign_hitl_approval(
    request_id: str,
    req: HITLSignRequest,
    current_user: User = Depends(require_role([UserRole.ARCHITECT, UserRole.AUDITOR])),
) -> HITLSignResponse:
    """Verifies Ed25519 digital signature of human auditor to release pending dispatch lock."""
    req_item = hitl_crypto_gate.get_request(request_id)
    if not req_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Approval request '{request_id}' not found.",
        )

    success = hitl_crypto_gate.sign_and_approve(
        request_id=request_id,
        approver_email=req.approver_email,
        public_key_hex=req.public_key_hex,
        signature_hex=req.ed25519_signature_hex,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cryptographic verification failed: Ed25519 signature is invalid for the specified public key and canonical message.",
        )

    return HITLSignResponse(
        id=request_id,
        status="APPROVED_SIGNED",
        signed_at=req_item.get("decided_at", ""),
        verified=True,
        message="Cryptographic signature verified. High-risk dispatch action unlocked.",
    )
