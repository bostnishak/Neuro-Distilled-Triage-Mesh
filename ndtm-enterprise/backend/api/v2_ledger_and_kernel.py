"""Cryptographic Merkle Audit Ledger & Speculative Kernel Router (NDTM v2.0)."""
from __future__ import annotations

import logging
from fastapi import APIRouter, HTTPException, status

from backend.inference_kernel.lora_hot_swapper import lora_hot_swapper
from backend.inference_kernel.speculative_decoder import speculative_engine
from backend.security_ledger.merkle_audit_chain import merkle_chain
from backend.schemas.v2_schemas import (
    ActiveAdaptersResponse,
    LoRASwapRequest,
    LoRASwapResponse,
    MerkleBlockItem,
    MerkleVerifyResponse,
    SpeculativeDecodeRequest,
    SpeculativeDecodeResponse,
)

logger = logging.getLogger("api.ledger_and_kernel")
router = APIRouter(prefix="", tags=["Security Ledger & Inference Kernel"])


@router.get("/ledger/chain", response_model=list[MerkleBlockItem])
async def list_merkle_audit_blocks() -> list[MerkleBlockItem]:
    """Returns the immutable sequential blocks of the cryptographic audit ledger."""
    return [
        MerkleBlockItem(
            seq_no=b.seq_no,
            event_id=b.event_id,
            event_type=b.event_type,
            actor_id=b.actor_id,
            canonical_payload=b.canonical_payload,
            payload_sha256=b.payload_sha256,
            prev_block_hash=b.prev_block_hash,
            block_hash=b.block_hash,
            merkle_root_snapshot=b.merkle_root_snapshot,
            created_at=b.created_at,
        )
        for b in merkle_chain.blocks
    ]


@router.post("/ledger/verify", response_model=MerkleVerifyResponse)
async def verify_merkle_chain_integrity() -> MerkleVerifyResponse:
    """Performs full cryptographic audit proof verifying SHA-256 block linkages and Merkle root."""
    res = merkle_chain.verify_chain_integrity()
    return MerkleVerifyResponse(
        valid=res["valid"],
        total_blocks_verified=res.get("total_blocks_verified", 0),
        merkle_root=res.get("merkle_root", ""),
        tampered_seq_no=res.get("tampered_seq_no"),
        reason=res.get("reason"),
    )


@router.post("/kernel/speculative", response_model=SpeculativeDecodeResponse)
async def execute_speculative_decoding(
    req: SpeculativeDecodeRequest,
) -> SpeculativeDecodeResponse:
    """Executes speculative draft token verification with Leviathan et al. rejection sampling."""
    res = speculative_engine.decode_prompt(
        prompt=req.prompt,
        max_tokens=req.max_tokens,
        draft_lookahead_k=req.draft_lookahead_k,
    )
    tokens_str = f"Speculative decoded ({len(res.tokens)} tokens with acceptance rate {res.acceptance_rate * 100:.1f}%)"
    return SpeculativeDecodeResponse(
        generated_text=tokens_str,
        acceptance_rate=res.acceptance_rate,
        draft_tokens_proposed=res.draft_tokens_proposed,
        tokens_accepted=res.tokens_accepted,
        speedup_ratio=res.speedup_ratio,
        resampled_count=res.resampled_count,
    )


@router.post("/kernel/lora/swap", response_model=LoRASwapResponse)
async def hot_swap_lora_adapter(req: LoRASwapRequest) -> LoRASwapResponse:
    """Hot-swaps the active LoRA adapter with atomic pointer transition and zero dropped coroutines."""
    try:
        swap_res = await lora_hot_swapper.swap_adapter(req.adapter_name)
        # Log event to cryptographic Merkle ledger
        merkle_chain.append_event(
            event_type="LORA_ADAPTER_SWAPPED",
            actor_id="OPERATOR_KERNEL_MGR",
            payload={"old": swap_res["previous_adapter"], "new": swap_res["active_adapter"], "checksum": swap_res["adapter_checksum_sha256"]},
        )
        return LoRASwapResponse(
            previous_adapter=swap_res["previous_adapter"],
            active_adapter=swap_res["active_adapter"],
            adapter_checksum_sha256=swap_res["adapter_checksum_sha256"],
            swapped_at=swap_res["swapped_at"],
        )
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))


@router.get("/kernel/adapters", response_model=ActiveAdaptersResponse)
async def get_active_lora_adapters() -> ActiveAdaptersResponse:
    """Returns currently loaded active adapter and catalog of pre-cached domain adapters."""
    return ActiveAdaptersResponse(
        active_adapter=lora_hot_swapper.active_adapter,
        available_adapters=lora_hot_swapper.list_adapters(),
    )
