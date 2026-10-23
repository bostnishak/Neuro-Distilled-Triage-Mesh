import datetime
import uuid
import numpy as np
import pytest
from domain.services.causal_digital_twin import CausalDigitalTwinEngine
from domain.services.byzantine_federated_mesh import ByzantineFederatedMesh
from domain.entities import InfrastructureNodeEntity, InfrastructureEdgeEntity
from domain.value_objects import GeoCoordinates, DifferentialPrivacyBudget


def test_causal_digital_twin_do_calculus():
    engine = CausalDigitalTwinEngine()
    now = datetime.datetime.now(datetime.timezone.utc)

    node_a = InfrastructureNodeEntity(
        id=uuid.UUID("10000000-0000-0000-0000-000000000001"),
        node_name="Node Gas Root",
        infra_type="GAS_PIPELINE",
        criticality=1.0,
        failure_probability=0.05,
        location=GeoCoordinates(latitude=41.0, longitude=28.9),
        created_at=now,
    )

    node_b = InfrastructureNodeEntity(
        id=uuid.UUID("10000000-0000-0000-0000-000000000002"),
        node_name="Node Power Plant",
        infra_type="ELECTRICAL_GRID",
        criticality=0.9,
        failure_probability=0.02,
        location=GeoCoordinates(latitude=41.01, longitude=28.91),
        created_at=now,
    )

    edge_ab = InfrastructureEdgeEntity(
        id=uuid.uuid4(),
        source_node_id=node_a.id,
        target_node_id=node_b.id,
        coupling_strength=0.8,
        cascade_latency_seconds=30,
        created_at=now,
    )

    engine.load_topology([node_a, node_b], [edge_ab])

    # Baseline loss
    base_probs = engine.do_intervention(str(node_a.id), 0.05)
    base_loss = engine.compute_expected_system_loss(base_probs)

    # Intervene: do(Node A = 1.0)
    failed_probs = engine.do_intervention(str(node_a.id), 1.0)
    failed_loss = engine.compute_expected_system_loss(failed_probs)

    assert failed_probs[str(node_b.id)] > base_probs[str(node_b.id)]
    assert failed_loss > base_loss


def test_byzantine_multi_krum_aggregation():
    # 5 honest workers, 2 byzantine rogue workers
    dim = 384
    rng = np.random.RandomState(42)

    honest_mean = rng.normal(0.0, 1.0, dim)
    honest_gradients = [honest_mean + rng.normal(0.0, 0.05, dim) for _ in range(5)]

    # Byzantine gradients: massive noise / sign flip
    byzantine_gradients = [
        honest_mean * -10.0 + rng.normal(0.0, 5.0, dim),
        rng.uniform(-100.0, 100.0, dim),
    ]

    node_ids = [f"honest_{i}" for i in range(5)] + ["byz_1", "byz_2"]
    all_gradients = honest_gradients + byzantine_gradients

    agg_grad, pruned, scores = ByzantineFederatedMesh.multi_krum(
        node_ids=node_ids,
        gradients=all_gradients,
        byzantine_tolerance_f=2,
    )

    assert "byz_1" in pruned
    assert "byz_2" in pruned
    # Aggregated gradient must be close to honest mean
    assert np.allclose(agg_grad, honest_mean, atol=0.2)


def test_renyi_differential_privacy():
    grad = np.ones(384, dtype=np.float32)
    budget = DifferentialPrivacyBudget(epsilon=2.0, delta=1e-5, alpha=4.0)

    privatized, expenditure = ByzantineFederatedMesh.apply_renyi_dp_noise(
        gradient_vector=grad,
        l2_clip_norm=1.0,
        dp_budget=budget,
    )

    assert privatized.shape == grad.shape
    assert expenditure > 0.0
    # Values should be perturbed
    assert not np.array_equal(privatized, grad)
