"""Gate 3: Mathematical, Cryptographic & Algorithmic Invariant Verification Suite.
Certifies PII TCKN checksums, Laplacian variance thresholds, Shannon entropy routing,
Z3 unsat_core self-correction, Leviathan speculative rejection sampling,
Pearl's do-calculus causal interventions, Byzantine Multi-Krum DP, and Merkle tree proofs.
"""
from __future__ import annotations

import asyncio
import base64
import math
import numpy as np
import pytest
import z3

import uuid
from uuid import UUID

from backend.causal_twin.blast_radius_simulator import BlastRadiusSimulator
from backend.causal_twin.counterfactual_engine import CounterfactualEngine
from backend.causal_twin.topology_graph import CausalTopologyGraph
from backend.core.exceptions import QualityGateFailedError
from backend.federated_mesh.byzantine_krum_aggregator import ByzantineKrumAggregator
from backend.federated_mesh.dp_gaussian_accountant import (
    GaussianDPAccountant,
    PrivacyBudgetExhaustedError,
)
from backend.inference_kernel.lora_hot_swapper import LoRAHotSwapper
from backend.inference_kernel.speculative_decoder import (
    SpeculativeDecodingEngine,
    rejection_sample_residual,
)
from backend.middleware.pii_scrubber import (
    PIIScrubber,
    validate_tckn_algorithm,
)
from backend.schemas.router import ExecutionTarget
from backend.schemas.symbolic import (
    FieldTeamDTO,
    IncidentTaskDTO,
    TaskAssignmentDTO,
)
from backend.security_ledger.merkle_audit_chain import MerkleAuditChain
from backend.services.image_forensics import ImageForensicsService
from backend.services.semantic_router import (
    CalibratedSemanticRouter,
    compute_normalized_shannon_entropy,
)
from backend.services.z3_symbolic_solver import NeuroSymbolicZ3Solver


# =============================================================================
# 1. PII & TCKN Checksum Invariant
# =============================================================================
class TestTCKNAlgorithmInvariant:
    """Proves Turkish National Identity (TCKN) Modulo-10/11 Checksum Laws."""

    def test_valid_vs_invalid_tckn(self):
        # Valid TCKNs satisfying:
        # d10 = ((sum(odd 1..9)*7) - sum(even 2..8)) % 10
        # d11 = sum(d1..d10) % 10
        valid_tckns = [
            "10000000146",
            "12345678950",
            "54321678950",
            "98765432150",
        ]
        for tckn in valid_tckns:
            assert validate_tckn_algorithm(tckn) is True, f"Failed valid TCKN: {tckn}"

        # Corrupted TCKNs
        invalid_tckns = [
            "10000000147",  # d11 off by 1
            "12345678951",  # d11 off by 1
            "02345678950",  # starts with 0
            "12345678901",  # random non-conforming digits
        ]
        for tckn in invalid_tckns:
            assert validate_tckn_algorithm(tckn) is False, f"False positive on invalid TCKN: {tckn}"

    def test_pii_scrubber_redaction_token(self):
        scrubber = PIIScrubber(salt="CERTIFICATION_SALT_2026")
        text = "Vatandas TCKN 10000000146 ve telefon 0532 111 22 33 bildirdi. Hat no 12345678901 kontrol edilsin."
        scrubbed, redactions = scrubber.scrub(text)

        # Valid TCKN must be scrubbed into [REDACTED_TCKN_<8_HEX>]
        assert "[REDACTED_TCKN_" in scrubbed
        assert "10000000146" not in scrubbed

        # Non-TCKN 11-digit number (12345678901) must remain untouched
        assert "12345678901" in scrubbed


import io
from PIL import Image, ImageFilter


# =============================================================================
# 2. Image Forensics & Laplacian Variance Threshold
# =============================================================================
class TestImageForensicsInvariants:
    """Proves Laplacian variance blur detection, polyglot rejection, and EXIF scrubbing."""

    def setup_method(self):
        self.service = ImageForensicsService(min_laplacian=85.0)

    def test_sharp_vs_blurred_vs_polyglot(self):
        # 1. Synthesize sharp checkerboard image (var > 500)
        sharp_pil = Image.new("RGB", (200, 200), (128, 128, 128))
        pixels = sharp_pil.load()
        for y in range(200):
            for x in range(200):
                if (x // 20 + y // 20) % 2 == 0:
                    pixels[x, y] = (255, 255, 255)
                else:
                    pixels[x, y] = (50, 50, 50)

        sharp_buf = io.BytesIO()
        sharp_pil.save(sharp_buf, format="PNG")
        sharp_b64 = f"data:image/png;base64,{base64.b64encode(sharp_buf.getvalue()).decode('utf-8')}"

        sharp_res = self.service.process_and_validate(sharp_b64)
        assert sharp_res.laplacian_variance > 500.0
        assert sharp_res.is_valid is True
        assert len(sharp_res.sha256_hash) == 64

        # 2. Synthesize Gaussian-blurred image (var < 30)
        blurred_pil = sharp_pil.filter(ImageFilter.GaussianBlur(radius=15))
        blurred_buf = io.BytesIO()
        blurred_pil.save(blurred_buf, format="PNG")
        blurred_b64 = f"data:image/png;base64,{base64.b64encode(blurred_buf.getvalue()).decode('utf-8')}"

        with pytest.raises(QualityGateFailedError) as exc_info:
            self.service.process_and_validate(blurred_b64)
        assert exc_info.value.reason == "IMAGE_TOO_BLURRY"
        assert exc_info.value.laplacian_score < 85.0

        # 3. Synthesize polyglot file starting with MZ header
        polyglot_bytes = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff\x00\x00" + b"\x00" * 100
        polyglot_b64 = f"data:image/png;base64,{base64.b64encode(polyglot_bytes).decode('utf-8')}"

        with pytest.raises(ValueError):
            self.service.process_and_validate(polyglot_b64)


# =============================================================================
# 3. DistillMesh Calibration, Shannon Entropy & OOD Routing Law
# =============================================================================
class TestDistillMeshRoutingLaws:
    """Proves normalized Shannon entropy bounds and 3-stage routing rules."""

    def test_uniform_entropy_routes_to_teacher(self):
        # 8-class uniform probability distribution [0.125, ..., 0.125]
        uniform_probs = np.ones(8, dtype=np.float32) / 8.0
        entropy = compute_normalized_shannon_entropy(uniform_probs)
        # Normalized entropy of uniform distribution must equal 1.0
        assert abs(entropy - 1.0) < 1e-4

        # Mock student producing high entropy
        class HighEntropyStudent:
            def predict(self, emb, temperature=1.0):
                return "UNCERTAIN", 0.125, 0.5, uniform_probs

        class FastMockEmbedder:
            def encode(self, text):
                return [0.1] * 384

        router = CalibratedSemanticRouter(onnx_engine=HighEntropyStudent(), embedder=FastMockEmbedder())
        # With high entropy H(p)=1.0 > 0.28, router MUST fallback to TEACHER
        res = asyncio.run(router.route_inference("Trafo civarında tanımlanamayan bir durum oluştu."))
        assert res.execution_target == ExecutionTarget.TEACHER_LLM_FALLBACK
        assert res.student_entropy == 1.0

    def test_peaked_entropy_routes_to_onnx(self):
        # Peaked probability distribution [0.98, 0.003, ...]
        peaked_probs = np.array([0.98, 0.003, 0.003, 0.003, 0.003, 0.003, 0.003, 0.002], dtype=np.float32)
        entropy = compute_normalized_shannon_entropy(peaked_probs)
        assert entropy < 0.20 <= 0.28

        class ConfidentStudent:
            def predict(self, emb, temperature=1.0):
                return "TRANSFORMER_FIRE", 0.98, 0.95, peaked_probs

        class FastMockEmbedder:
            def encode(self, text):
                return [0.1] * 384

        router = CalibratedSemanticRouter(onnx_engine=ConfidentStudent(), embedder=FastMockEmbedder())
        res = asyncio.run(router.route_inference("Elektrik trafosu patladı, alevler yükseliyor."))
        assert res.execution_target == ExecutionTarget.ONNX_STUDENT_INT8
        assert res.student_entropy < 0.28
        assert res.latency_ms < 50.0


# =============================================================================
# 4. Z3 unsat_core Extraction & Self-Correction Proof
# =============================================================================
class TestZ3UnsatCoreAndProof:
    """Proves Z3 unsat_core conflict extraction, repair loop convergence, and SMT-LIB v2 proof parsing."""

    def test_unsat_core_and_convergence(self):
        solver = NeuroSymbolicZ3Solver(max_iterations=3)

        inc_id = UUID("11111111-1111-1111-1111-111111111111")
        team_bravo_id = UUID("22222222-2222-2222-2222-222222222222")
        team_alfa_id = UUID("33333333-3333-3333-3333-333333333333")

        incidents = [
            IncidentTaskDTO(
                id=inc_id,
                category="ELECTRICAL_GRID",
                urgency_score=10,
                required_skills=["HIGH_VOLTAGE"],
                estimated_work_minutes=45,
                latitude=41.0082,
                longitude=28.9784,
            )
        ]
        teams = [
            FieldTeamDTO(
                id=team_bravo_id,
                team_code="TEAM_BRAVO_FIBER",
                skills=["FIBER_OPTIC"],
                shift_remaining_minutes=10,
                max_concurrent_tasks=1,
                latitude=41.0082,
                longitude=28.9784,
                is_available=True,
            ),
            FieldTeamDTO(
                id=team_alfa_id,
                team_code="TEAM_ALFA_VOLTAGE",
                skills=["HIGH_VOLTAGE", "TRANSFORMER"],
                shift_remaining_minutes=360,
                max_concurrent_tasks=2,
                latitude=41.0082,
                longitude=28.9784,
                is_available=True,
            ),
        ]
        flawed_proposal = [
            TaskAssignmentDTO(
                incident_id=inc_id,
                team_id=team_bravo_id,
                estimated_travel_minutes=5,
                estimated_work_minutes=45,
                arrival_time_minutes=5,
            )
        ]

        result = solver.execute_self_correcting_loop(incidents, teams, initial_proposal=flawed_proposal)

        # Iteration 1 must have encountered UNSAT and extracted conflicting clauses
        assert result.iterations_executed >= 2
        first_iter = result.iteration_history[0]
        assert first_iter.status == "UNSAT"
        assert any("SKILL_MISMATCH" in c or "SHIFT_OVERFLOW" in c for c in first_iter.unsat_core_conflicts)

        # Self-correction loop must converge to SAT with verified assignments
        assert result.is_sat is True
        assert len(result.assignments) == 1
        assert result.assignments[0].team_id == team_alfa_id

        # Validate SMT-LIB v2 proof output
        smt2_string = result.z3_proof_smt2
        assert len(smt2_string) > 20
        assert "assert" in smt2_string.lower() or "declare-fun" in smt2_string.lower()


# =============================================================================
# 5. Speculative Decoding Rejection Sampling & LoRA Atomic Swap
# =============================================================================
class TestSpeculativeKernelAndLoRA:
    """Proves Leviathan et al. rejection sampling normalization and zero-drop LoRA hot-swapping."""

    def test_rejection_sampling_normalization(self):
        # Case A: p(x) >= q(x)
        p = np.array([0.7, 0.2, 0.1], dtype=np.float64)
        q = np.array([0.5, 0.3, 0.2], dtype=np.float64)

        # Residual distribution p'(x) must sum to 1.0 +- 1e-6
        p_prime = rejection_sample_residual(p, q)
        assert abs(float(np.sum(p_prime)) - 1.0) < 1e-6
        assert np.all(p_prime >= 0.0)

    def test_concurrent_lora_hot_swap(self):
        swapper = LoRAHotSwapper(initial_adapter="DEFAULT_MUNICIPAL")

        async def run_test():
            # Fire 50 concurrent async inference coroutines
            async def worker(idx):
                res = await swapper.run_inference(f"Incident report #{idx}")
                assert res["status"] == "SUCCESS"
                assert len(res["checksum"]) == 64
                return res

            # Trigger LoRA swap mid-flight
            async def trigger_swap():
                await asyncio.sleep(0.001)
                swap_res = await swapper.swap_adapter("TELECOM_FIBER")
                assert swap_res["active_adapter"] == "TELECOM_FIBER"

            tasks = [worker(i) for i in range(50)] + [trigger_swap()]
            results = await asyncio.gather(*tasks)
            assert len(results) == 51

        asyncio.run(run_test())
        assert swapper.active_adapter == "TELECOM_FIBER"


# =============================================================================
# 6. Causal DAG Blast-Radius & Pearl's Do-Calculus Intervention
# =============================================================================
class TestCausalDigitalTwinDoCalculus:
    """Proves structural intervention on mutilated graph G_{X-bar} strictly reduces risk."""

    def test_do_calculus_intervention_mitigates_risk(self):
        graph = CausalTopologyGraph()
        engine = CounterfactualEngine(graph)

        # Initial failure at SUBSTATION_IKITELLI
        res = engine.evaluate_intervention(
            failed_node_code="SUBSTATION_IKITELLI",
            intervened_node_code="FIBER_BOGAZICI_NORTH",
            intervention_action="REINFORCED",
        )

        assert res["original_risk_rating"] > 0.0
        assert res["counterfactual_risk_rating"] < res["original_risk_rating"]
        assert res["delta_crr"] > 0.0
        assert res["is_risk_mitigated"] is True
        assert len(res["mutilated_edges_severed"]) > 0


# =============================================================================
# 7. Byzantine Multi-Krum & (epsilon, delta)-Differential Privacy
# =============================================================================
class TestByzantineKrumAndDifferentialPrivacy:
    """Proves Byzantine isolation, L2 gradient clipping, and DP budget exhaustion."""

    def test_multi_krum_byzantine_isolation(self):
        aggregator = ByzantineKrumAggregator(f_byzantine=1)
        # 5 honest vectors centered at g_true
        g_true = np.ones(384, dtype=np.float64) * 0.05
        honest_vectors = [g_true + np.random.normal(0, 0.002, size=384) for _ in range(5)]
        # 1 Byzantine poisoned vector
        poisoned_vector = -50.0 * g_true

        all_vectors = honest_vectors + [poisoned_vector]
        res = aggregator.aggregate(all_vectors)

        # Poisoned node (index 5) must be assigned the highest distance score and isolated
        poison_idx = 5
        assert poison_idx in res.byzantine_indices
        assert poison_idx not in res.selected_indices
        assert res.scores[poison_idx] > max(res.scores[i] for i in range(5))

    def test_dp_clipping_and_budget_exhaustion(self):
        accountant = GaussianDPAccountant(max_epsilon=5.0, delta=1e-5, clip_norm=1.0, noise_multiplier=1.2)

        # L2 norm clipping test
        large_vector = np.ones(384, dtype=np.float64) * 10.0
        clipped = accountant.clip_gradient(large_vector)
        assert np.linalg.norm(clipped) <= 1.0 + 1e-6

        # Step until budget exhaustion
        exhausted = False
        try:
            for _ in range(50):
                accountant.spend_step()
        except PrivacyBudgetExhaustedError:
            exhausted = True

        assert exhausted is True, "PrivacyBudgetExhaustedError was not raised upon exceeding epsilon_max!"


# =============================================================================
# 8. Cryptographic Merkle Tree Tamper Detection
# =============================================================================
class TestMerkleAuditChainTamperDetection:
    """Proves SHA-256 block hash chaining and 100% tamper detection."""

    def test_merkle_tamper_detection(self):
        chain = MerkleAuditChain()

        # Append 10 audit events
        for i in range(1, 11):
            chain.append_event(
                event_type=f"AUDIT_DISPATCH_STEP_{i}",
                actor_id=f"OPERATOR_NODE_{i % 3}",
                payload={"step": i, "status": "DISPATCH_AUTHORIZED"},
            )

        # Chain must initially verify as valid
        init_verify = chain.verify_chain_integrity()
        assert init_verify["valid"] is True
        assert init_verify["total_blocks_verified"] == 11  # Genesis + 10 events
        assert init_verify["tampered_seq_no"] is None

        # Inject SQL UPDATE tampering on seq_no 4
        chain.tamper_block_for_testing(seq_no=4, malicious_payload={"hacked": True})

        # Chain verification must immediately detect tampering at block 4
        tamper_verify = chain.verify_chain_integrity()
        assert tamper_verify["valid"] is False
        assert tamper_verify["tampered_seq_no"] == 4
        assert tamper_verify["reason"] == "PAYLOAD_OR_CHAIN_HASH_MISMATCH"
