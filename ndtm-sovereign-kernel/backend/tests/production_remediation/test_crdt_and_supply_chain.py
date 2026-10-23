"""
Test Suite: Multi-Region CRDT Mesh & Cryptographic Model Supply Chain + KMS
Verifies:
1. VectorClock partial ordering, causality, and join-semilattice merge.
2. PNCounter and LWWElementSet convergence across active-active WAN replicas.
3. Ed25519 model supply chain signature generation, validation, and tamper detection.
4. AES-256-GCM envelope KMS encryption, decryption, and KEK rotation.
"""

import tempfile
from pathlib import Path
import pytest

from engines_v3_hardened.crdt_multiregion_replicator import (
    VectorClock,
    PNCounter,
    LWWElementSet,
    ActiveActiveMeshReplicator,
)
from core.model_supply_chain_signer import (
    ModelSupplyChainSigner,
    ModelTamperedSecurityException,
)
from core.envelope_kms_vault import EnvelopeKMSVault


def test_crdt_vector_clock_and_pn_counter():
    vc1 = VectorClock({"us": 2, "eu": 1})
    vc2 = VectorClock({"us": 1, "eu": 3})

    assert vc1.is_concurrent_with(vc2) is True
    vc_merged = vc1.merge(vc2)
    assert vc_merged.clock == {"us": 2, "eu": 3}

    pn1 = PNCounter({"us": 5}, {"us": 1})
    pn2 = PNCounter({"eu": 4}, {"eu": 2})
    assert pn1.value == 4
    assert pn2.value == 2

    pn_merged = pn1.merge(pn2)
    # Total: (5 + 4) - (1 + 2) = 6
    assert pn_merged.value == 6


def test_crdt_active_active_mesh_replication():
    r_us = ActiveActiveMeshReplicator("us-west-1")
    r_eu = ActiveActiveMeshReplicator("eu-central-1")

    # Concurrent writes in US and EU
    r_us.local_open_incident("inc_us_01")
    r_eu.local_open_incident("inc_eu_01")

    # Exchange deltas across WAN
    delta_us = r_us.export_sync_delta()
    delta_eu = r_eu.export_sync_delta()

    r_us.ingest_sync_delta(delta_eu)
    r_eu.ingest_sync_delta(delta_us)

    st_us = r_us.get_mesh_status()
    st_eu = r_eu.get_mesh_status()

    # Both regions must be 100% converged to identical sets
    assert st_us["active_incidents_count"] == 2
    assert st_eu["active_incidents_count"] == 2
    assert st_us["active_incident_ids"] == ["inc_eu_01", "inc_us_01"]
    assert st_eu["active_incident_ids"] == ["inc_eu_01", "inc_us_01"]


def test_ed25519_model_supply_chain_verification():
    priv, priv_hex, pub_hex = ModelSupplyChainSigner.generate_keypair()
    signer = ModelSupplyChainSigner(trusted_public_keys_hex=[pub_hex])

    with tempfile.NamedTemporaryFile(suffix=".onnx", delete=False) as art_file:
        art_file.write(b"GENUINE_SOVEREIGN_ONNX_MODEL_BINARY_WEIGHTS_4096_BYTES")
        art_path = Path(art_file.name)

    manifest_path = Path(str(art_path) + ".sig")
    signer.sign_model_artifact(
        art_path,
        priv,
        model_name="student_quantized",
        version="v3.0.0",
        output_manifest_path=manifest_path,
    )

    # 1. Genuine artifact must verify True
    assert signer.verify_model_artifact(art_path, manifest_path) is True

    # 2. Tampered artifact (single byte alteration) must raise ModelTamperedSecurityException
    with open(art_path, "wb") as f:
        f.write(b"TAMPERED_BACKDOOR_ONNX_WEIGHTS")

    with pytest.raises(ModelTamperedSecurityException):
        signer.verify_model_artifact(art_path, manifest_path)

    # Cleanup
    art_path.unlink(missing_ok=True)
    manifest_path.unlink(missing_ok=True)


def test_envelope_kms_encryption_and_rotation():
    kms = EnvelopeKMSVault()
    assert kms.current_kek_version == 1

    secret_data = b"CRITICAL_INCIDENT_SURGE_RESPONSE_COORDINATES"
    tenant_id = "metro_fire_dispatch_unit_09"

    # Encrypt
    envelope = kms.encrypt(tenant_id, secret_data)
    assert envelope.kek_version == 1

    # Decrypt
    decrypted = kms.decrypt(envelope)
    assert decrypted == secret_data

    # Rotate Master KEK to v2
    new_v = kms.rotate_master_kek()
    assert new_v == 2

    # Re-wrap envelope to v2 without bulk data re-encryption
    rewrapped = kms.rewrap_envelope(envelope)
    assert rewrapped.kek_version == 2
    assert rewrapped.ciphertext_b64 == envelope.ciphertext_b64  # Bulk data untouched

    # Decrypt re-wrapped payload under v2
    decrypted_v2 = kms.decrypt(rewrapped)
    assert decrypted_v2 == secret_data
