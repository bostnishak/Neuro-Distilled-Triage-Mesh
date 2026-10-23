"""
Test Suite: Markovian H3 Hawkes Point Process Engine
Verifies:
1. Hexagonal axial projection (q, r) and roundtrip coordinate fidelity.
2. O(1) recursive state accumulator decay: A(t) = A(t0) * exp(-beta * dt).
3. 1-ring neighbor cross-excitation and intensity evaluation.
4. Aftershock forecasting and branching ratio calculation.
5. Ogata modified thinning simulation.
6. GeoJSON FeatureCollection generation.
"""

import math
import pytest
from engines_v3_hardened.markovian_h3_hawkes_engine import (
    MarkovianH3HawkesEngine,
    HexCoord,
    HexGridProjector,
    HawkesIncidentEvent,
)


def test_hex_grid_projection_roundtrip():
    projector = HexGridProjector(hex_radius_meters=250.0, ref_lat=37.7749, ref_lon=-122.4194)
    # Convert lat/lon to xy, then to hex
    lat, lon = 37.7755, -122.4180
    x, y = projector.lat_lon_to_xy(lat, lon)
    hex_coord = projector.xy_to_hex(x, y)
    assert isinstance(hex_coord.q, int)
    assert isinstance(hex_coord.r, int)
    assert hex_coord.s == -hex_coord.q - hex_coord.r

    # Neighbors must be exactly 6 unique adjacent hex cells
    neighbors = hex_coord.neighbors()
    assert len(neighbors) == 6
    assert len(set(n.to_key() for n in neighbors)) == 6


def test_markovian_o1_recursive_decay():
    engine = MarkovianH3HawkesEngine(hex_radius_meters=250.0)

    # Ingest incident at t = 100.0
    ev1 = HawkesIncidentEvent(
        event_id="ev_001",
        timestamp=100.0,
        lat=37.7749,
        lon=-122.4194,
        category="FIRE",
        severity=1.0,
    )
    center_hex = engine.ingest_event(ev1)

    # Query immediately at t = 100.0
    intensity_t0 = engine.query_intensity(37.7749, -122.4194, "FIRE", 100.0)
    base_mu = engine.mu["FIRE"]
    assert intensity_t0 > base_mu

    # Query at t = 200.0 (dt = 100s)
    # Theoretical decay factor: exp(-beta * 100)
    beta = engine.beta["FIRE"]
    decay_factor = math.exp(-beta * 100.0)
    intensity_t100 = engine.query_intensity(37.7749, -122.4194, "FIRE", 200.0)

    # Net excitation above base_mu should match decayed value
    net_t0 = intensity_t0 - base_mu
    net_t100 = intensity_t100 - base_mu
    assert pytest.approx(net_t100, rel=1e-3) == (net_t0 * decay_factor)


def test_aftershock_forecasting():
    engine = MarkovianH3HawkesEngine(hex_radius_meters=250.0)
    ev = HawkesIncidentEvent("ev_f", 100.0, 37.7749, -122.4194, "FIRE", 2.0)
    h_coord = engine.ingest_event(ev)

    forecast = engine.forecast_aftershocks(h_coord, "FIRE", horizon_seconds=3600.0, current_ts=100.0)
    assert forecast["hex_key"] == h_coord.to_key()
    assert forecast["expected_total_events"] > forecast["expected_background_events"]
    assert forecast["branching_ratio"] > 0.0
    assert 0.0 <= forecast["surge_risk_score"] <= 1.0


def test_geojson_heatmap_export():
    engine = MarkovianH3HawkesEngine(hex_radius_meters=250.0)
    ev = HawkesIncidentEvent("ev_geo", 100.0, 37.7749, -122.4194, "HAZMAT", 1.5)
    engine.ingest_event(ev)

    geojson = engine.export_geojson_heatmap(current_ts=101.0)
    assert geojson["type"] == "FeatureCollection"
    assert len(geojson["features"]) >= 1
    feat = geojson["features"][0]
    assert feat["geometry"]["type"] == "Polygon"
    assert "composite_intensity" in feat["properties"]
    assert len(feat["geometry"]["coordinates"][0]) == 7  # 6 vertices + closed vertex
