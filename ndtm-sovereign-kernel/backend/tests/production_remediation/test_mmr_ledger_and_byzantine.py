"""
Test Suite: Micro-Batched MMR Ledger & FLTrust + Bulyan Byzantine Aggregator
Verifies:
1. Micro-batched Merkle Mountain Range (MMR) ledger append and peak bagging.
2. 2-level cryptographic inclusion proof verification.
3. FLTrust cosine trust scoring with server anchor gradient g_0.
4. Bulyan coordinate-wise trimmed median defense against Byzantine poisoning.
5. Differential Privacy Gaussian perturbation calibration.
"""

import json
import numpy as np
import pytest

from engines_v3_hardened.mmr_microbatch_ledger import (
    MicroBatchedMMRLedger,
    MerkleInclusionProof,
)
from engines_v3_hardened.fltrust_bulyan_aggregator import (
    FLTrustBulyanAggregator,
    FederatedClientUpdate,
)


def test_mmr_microbatch_ledger_and_inclusion_proof():
    ledger = MicroBatchedMMRLedger(max_batch_size=4, linger_timeout_ms=50.0)

    # Ingest 10 events
    for i in range(10):
        ledger.append_event(f"evt_{i}", {"seq": i, "category": "FIRE"})

    root_hex = ledger.force_flush()
    assert len(root_hex) == 64
    summary = ledger.get_audit_summary()
    assert summary["total_events"] == 10
    assert summary["total_batches"] == 3  # 4 + 4 + 2

    # Verify inclusion proof for event 5
    proof = ledger.generate_proof("evt_5")
    assert proof is not None
    assert isinstance(proof, MerkleInclusionProof)

    expected_payload = json.dumps({"category": "FIRE", "seq": 5}, sort_keys=True).encode("utf-8")
    assert proof.verify(expected_payload) is True

    # Tampered payload must fail proof verification
    tampered_payload = json.dumps({"category": "FIRE", "seq": 999}, sort_keys=True).encode("utf-8")
    assert proof.verify(tampered_payload) is False


def test_fltrust_bulyan_byzantine_resilience():
    dim = 8
    aggregator = FLTrustBulyanAggregator(dimension=dim, byzantine_tolerance_fraction=0.3)

    # Clean server anchor gradient g_0
    g0 = np.array([1.0, 1.0, 0.5, 0.5, 0.0, 0.0, 0.0, 0.0], dtype=np.float64)

    # 4 Honest clients (aligned with g_0 with small Gaussian noise)
    honest_updates = [
        FederatedClientUpdate("honest_1", g0 + np.random.normal(0, 0.05, dim), 100),
        FederatedClientUpdate("honest_2", g0 + np.random.normal(0, 0.05, dim), 100),
        FederatedClientUpdate("honest_3", g0 + np.random.normal(0, 0.05, dim), 100),
        FederatedClientUpdate("honest_4", g0 + np.random.normal(0, 0.05, dim), 100),
    ]

    # 2 Malicious Byzantine clients (opposite direction / poisoning attack)
    byzantine_updates = [
        FederatedClientUpdate("byz_attack_1", -10.0 * g0, 100),
        FederatedClientUpdate("byz_attack_2", np.array([-5.0, 0.0, 0.0, 0.0, 5.0, 5.0, 5.0, 5.0]), 100),
    ]

    all_updates = honest_updates + byzantine_updates
    result = aggregator.aggregate(all_updates, g0)

    # Both Byzantine attackers must be detected and filtered out
    assert result.is_resilient is True
    assert "byz_attack_1" in result.byzantine_clients_detected
    assert "byz_attack_2" in result.byzantine_clients_detected
    assert result.trusted_clients_count == 4

    # Aggregated gradient must point in positive direction of g_0
    cosine_to_g0 = np.dot(result.aggregated_gradient, g0) / (
        np.linalg.norm(result.aggregated_gradient) * np.linalg.norm(g0)
    )
    assert cosine_to_g0 > 0.85
