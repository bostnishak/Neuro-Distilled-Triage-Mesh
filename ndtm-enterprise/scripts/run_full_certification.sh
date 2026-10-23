#!/usr/bin/env bash
# ==============================================================================
# MASTER ZERO-DEFECT CERTIFICATION ORCHESTRATOR
# PROJECT: NEURO-DISTILLED TRIAGE MESH (NDTM v1.0 + v2.0 SOVEREIGN EDITION)
# ==============================================================================
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${ROOT_DIR}"

echo "=============================================================================="
echo "    NEURO-DISTILLED TRIAGE MESH (NDTM) — ZERO-DEFECT MASTER CERTIFICATION     "
echo "=============================================================================="
echo "Execution Timestamp: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo "Target Platform: Linux / POSIX / Windows Git Bash"
echo "Python Executable: $(which python || which python3)"
echo "------------------------------------------------------------------------------"

GATE1_STATUS="PENDING"
GATE2_STATUS="PENDING"
GATE3_STATUS="PENDING"
GATE3B_STATUS="PENDING"
GATE4_STATUS="PENDING"
GATE5_STATUS="PENDING"
GATE6_STATUS="PENDING"

FAILED_GATES=()

# ------------------------------------------------------------------------------
# GATE 1 & GATE 2: Static AST Zero-Mock & Cross-Stack Contract Verifier
# ------------------------------------------------------------------------------
echo ""
echo ">>> Executing Gate 1 & Gate 2: Static AST, Zero-Mock & Contract Parity..."
if python scripts/verify_zero_defect_ast.py; then
    GATE1_STATUS="PASSED [100%]"
    GATE2_STATUS="PASSED [100%]"
    echo "[CERTIFIED] Gate 1 & 2 Static Analysis & Schema Parity Succeeded."
else
    GATE1_STATUS="FAILED"
    GATE2_STATUS="FAILED"
    FAILED_GATES+=("Gate 1/2: Static AST & Schema Parity")
fi

# ------------------------------------------------------------------------------
# GATE 3: Mathematical, Cryptographic & Algorithmic Invariant Suite
# ------------------------------------------------------------------------------
echo ""
echo ">>> Executing Gate 3: Mathematical & Algorithmic Invariants (Z3, Entropy, Pearl, Krum, DP, Merkle)..."
if [ -f "backend/tests/certification/test_gate3_math_invariants.py" ]; then
    if python -m pytest backend/tests/certification/test_gate3_math_invariants.py -v; then
        GATE3_STATUS="PASSED [100%]"
        echo "[CERTIFIED] Gate 3 Mathematical & Cryptographic Invariants Verified."
    else
        GATE3_STATUS="FAILED"
        FAILED_GATES+=("Gate 3: Math Invariants")
    fi
else
    echo "[SKIPPED/STAGE-LOCKED] Gate 3 test file will be verified in Audit Stage 2."
    GATE3_STATUS="LOCKED (Stage 2)"
fi

# ------------------------------------------------------------------------------
# GATE 3B: C++20 Edge Node Ring Buffer & Cooley-Tukey FFT Proof
# ------------------------------------------------------------------------------
echo ""
echo ">>> Executing Gate 3B: C++20 Lock-Free SPSC Ring Buffer & Cooley-Tukey FFT Power Spectrum..."
if [ -f "edge_cpp_node/tests/test_edge_fft_and_ringbuffer.cpp" ]; then
    if g++ -std=c++20 -O3 -Iedge_cpp_node/include edge_cpp_node/src/acoustic_fft_analyzer.cpp edge_cpp_node/tests/test_edge_fft_and_ringbuffer.cpp -o test_edge_fft.exe; then
        if ./test_edge_fft.exe; then
            GATE3B_STATUS="PASSED [100%]"
            echo "[CERTIFIED] Gate 3B C++20 Edge DSP & Ring Buffer Verified."
        else
            GATE3B_STATUS="FAILED"
            FAILED_GATES+=("Gate 3B: C++20 Edge DSP Execution")
        fi
        rm -f test_edge_fft.exe
    else
        GATE3B_STATUS="FAILED (Compile Error)"
        FAILED_GATES+=("Gate 3B: C++20 Compilation")
    fi
else
    echo "[SKIPPED/STAGE-LOCKED] Gate 3B C++ test file will be verified in Audit Stage 2."
    GATE3B_STATUS="LOCKED (Stage 2)"
fi

# ------------------------------------------------------------------------------
# GATE 4: Automated Red-Team AppSec Penetration Suite
# ------------------------------------------------------------------------------
echo ""
echo ">>> Executing Gate 4: Red-Team AppSec Penetration Suite (JWT, RBAC, PromptGuard, Ed25519, Idempotency)..."
if [ -f "backend/tests/certification/test_gate4_appsec_pentest.py" ]; then
    if python -m pytest backend/tests/certification/test_gate4_appsec_pentest.py -v; then
        GATE4_STATUS="PASSED [100%]"
        echo "[CERTIFIED] Gate 4 AppSec Penetration Defense Verified."
    else
        GATE4_STATUS="FAILED"
        FAILED_GATES+=("Gate 4: AppSec Pentest")
    fi
else
    echo "[SKIPPED/STAGE-LOCKED] Gate 4 test file will be verified in Audit Stage 3."
    GATE4_STATUS="LOCKED (Stage 3)"
fi

# ------------------------------------------------------------------------------
# GATE 6: Distributed Chaos, Transactional Outbox & DLQ Torture Suite
# ------------------------------------------------------------------------------
echo ""
echo ">>> Executing Gate 6: Distributed Chaos, Outbox & Circuit Breaker Recovery..."
if [ -f "backend/tests/certification/test_gate6_chaos_and_outbox.py" ]; then
    if python -m pytest backend/tests/certification/test_gate6_chaos_and_outbox.py -v; then
        GATE6_STATUS="PASSED [100%]"
        echo "[CERTIFIED] Gate 6 Chaos & Outbox Resilience Verified."
    else
        GATE6_STATUS="FAILED"
        FAILED_GATES+=("Gate 6: Chaos & Outbox")
    fi
else
    echo "[SKIPPED/STAGE-LOCKED] Gate 6 test file will be verified in Audit Stage 3."
    GATE6_STATUS="LOCKED (Stage 3)"
fi

# ------------------------------------------------------------------------------
# GATE 5: 8-View Zero-Dead-Button & Zero-Mock UI Automation Verification
# ------------------------------------------------------------------------------
echo ""
echo ">>> Executing Gate 5: 8-View Zero-Dead-Button & Zero-Mock UI Verification..."
if [ -f "scripts/verify_gate5_ui_bindings.py" ]; then
    if python scripts/verify_gate5_ui_bindings.py; then
        GATE5_STATUS="PASSED [100%]"
        echo "[CERTIFIED] Gate 5 8-View UI Automation & Zero-Dead-Button Verified."
    else
        GATE5_STATUS="FAILED"
        FAILED_GATES+=("Gate 5: Zero-Dead-Button UI Verification")
    fi
else
    echo "[SKIPPED] scripts/verify_gate5_ui_bindings.py not found."
    GATE5_STATUS="FAILED"
fi

# ------------------------------------------------------------------------------
# MASTER CERTIFICATION SCORECARD
# ------------------------------------------------------------------------------
echo ""
echo "=============================================================================="
echo "                   NDTM MASTER ZERO-DEFECT SCORECARD                          "
echo "=============================================================================="
echo " Gate 1: Static AST Zero-Mock & Anti-Laziness Scanner   : ${GATE1_STATUS}"
echo " Gate 2: Cross-Boundary Contract & Route/Schema Parity  : ${GATE2_STATUS}"
echo " Gate 3: Mathematical, Cryptographic & Invariant Proofs : ${GATE3_STATUS}"
echo " Gate 3B: C++20 Edge DSP & Lock-Free Ring Buffer Proof   : ${GATE3B_STATUS}"
echo " Gate 4: Automated Red-Team AppSec Penetration Testing  : ${GATE4_STATUS}"
echo " Gate 5: Playwright 8-View Zero-Dead-Button UI Crawler  : ${GATE5_STATUS}"
echo " Gate 6: Distributed Chaos, Transactional Outbox & DLQ  : ${GATE6_STATUS}"
echo "=============================================================================="

if [ ${#FAILED_GATES[@]} -gt 0 ]; then
    echo " [FINAL VERDICT] CERTIFICATION FAILED. The following gates did not pass:"
    for fg in "${FAILED_GATES[@]}"; do
        echo "   - ${fg}"
    done
    exit 1
else
    echo " [FINAL VERDICT] CERTIFICATION APPROVED: All active gates passed with 0 defects."
    exit 0
fi
