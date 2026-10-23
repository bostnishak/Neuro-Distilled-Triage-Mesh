"""
Neuro-Distilled Triage Mesh (NDTM) — Sovereign Distributed & Failure-Proof Kernel
RFC-NDTM-OMEGA: Production Hardening Engine v3.0

Phase 27: Markovian H3 Hawkes Process Engine
O(1) Recursive Decay Spatio-Temporal Point Process with Hexagonal Spatial Discretization.
"""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass(frozen=True)
class HexCoord:
    """Axial coordinates (q, r) for a regular hexagonal grid."""
    q: int
    r: int

    @property
    def s(self) -> int:
        """Cube coordinate s = -q - r."""
        return -self.q - self.r

    def to_key(self) -> str:
        return f"{self.q}:{self.r}"

    @classmethod
    def from_key(cls, key: str) -> HexCoord:
        parts = key.split(":")
        return cls(q=int(parts[0]), r=int(parts[1]))

    def neighbors(self) -> List[HexCoord]:
        """Returns the 6 1-ring adjacent hexagonal neighbors."""
        axial_directions = [
            (1, 0), (1, -1), (0, -1),
            (-1, 0), (-1, 1), (0, 1)
        ]
        return [HexCoord(self.q + dq, self.r + dr) for dq, dr in axial_directions]


class HexGridProjector:
    """
    Projects WGS-84 (lat, lon) coordinates to metric local tangent plane,
    and quantizes into regular hexagonal cells of outer radius R (meters).
    Uses pointy-topped orientation.
    """

    EARTH_RADIUS_METERS: float = 6378137.0

    def __init__(self, hex_radius_meters: float = 250.0, ref_lat: float = 37.7749, ref_lon: float = -122.4194):
        self.r_hex = float(hex_radius_meters)
        self.ref_lat = ref_lat
        self.ref_lon = ref_lon
        self.ref_lat_rad = math.radians(ref_lat)
        self.ref_lon_rad = math.radians(ref_lon)
        self.cos_ref_lat = math.cos(self.ref_lat_rad)

    def lat_lon_to_xy(self, lat: float, lon: float) -> Tuple[float, float]:
        """Equirectangular projection to metric (x, y) relative to reference anchor."""
        lat_rad = math.radians(lat)
        lon_rad = math.radians(lon)
        x = self.EARTH_RADIUS_METERS * (lon_rad - self.ref_lon_rad) * self.cos_ref_lat
        y = self.EARTH_RADIUS_METERS * (lat_rad - self.ref_lat_rad)
        return x, y

    def xy_to_lat_lon(self, x: float, y: float) -> Tuple[float, float]:
        """Inverse projection from metric (x, y) back to WGS-84 (lat, lon)."""
        lat_rad = self.ref_lat_rad + (y / self.EARTH_RADIUS_METERS)
        lon_rad = self.ref_lon_rad + (x / (self.EARTH_RADIUS_METERS * self.cos_ref_lat))
        return math.degrees(lat_rad), math.degrees(lon_rad)

    def xy_to_hex(self, x: float, y: float) -> HexCoord:
        """Converts metric (x, y) to closest hexagonal axial coordinate (q, r)."""
        # Pointy-topped hexagon projection
        # x = R * sqrt(3) * (q + r/2)
        # y = R * (3/2) * r
        q_frac = (math.sqrt(3.0) / 3.0 * x - (1.0 / 3.0) * y) / self.r_hex
        r_frac = (2.0 / 3.0 * y) / self.r_hex
        s_frac = -q_frac - r_frac

        # Cube coordinate rounding
        q_round = round(q_frac)
        r_round = round(r_frac)
        s_round = round(s_frac)

        q_diff = abs(q_round - q_frac)
        r_diff = abs(r_round - r_frac)
        s_diff = abs(s_round - s_frac)

        if q_diff > r_diff and q_diff > s_diff:
            q_round = -r_round - s_round
        elif r_diff > s_diff:
            r_round = -q_round - s_round

        return HexCoord(q=int(q_round), r=int(r_round))

    def hex_to_center_xy(self, hex_coord: HexCoord) -> Tuple[float, float]:
        """Returns the metric center (x, y) of the specified hexagonal cell."""
        x = self.r_hex * math.sqrt(3.0) * (hex_coord.q + hex_coord.r / 2.0)
        y = self.r_hex * 1.5 * hex_coord.r
        return x, y

    def hex_to_center_lat_lon(self, hex_coord: HexCoord) -> Tuple[float, float]:
        """Returns the WGS-84 (lat, lon) center of the specified hexagonal cell."""
        x, y = self.hex_to_center_xy(hex_coord)
        return self.xy_to_lat_lon(x, y)

    def hex_to_polygon_lat_lon(self, hex_coord: HexCoord) -> List[Tuple[float, float]]:
        """Returns the 6 vertices of the hexagon polygon in (lat, lon) coordinates."""
        cx, cy = self.hex_to_center_xy(hex_coord)
        vertices: List[Tuple[float, float]] = []
        for i in range(6):
            angle_rad = math.radians(60.0 * i - 30.0)
            vx = cx + self.r_hex * math.cos(angle_rad)
            vy = cy + self.r_hex * math.sin(angle_rad)
            lat, lon = self.xy_to_lat_lon(vx, vy)
            vertices.append((lat, lon))
        vertices.append(vertices[0])  # Close polygon
        return vertices


@dataclass
class HexCellState:
    """
    O(1) Markovian Hawkes State Accumulator for a single hexagonal cell.
    A_{h, c}(t) decays exponentially with parameter beta_c.
    """
    hex_coord: HexCoord
    last_update_ts: float
    # category -> accumulated excitation value
    accumulators: Dict[str, float] = field(default_factory=dict)
    event_count: int = 0

    def decay_to(self, current_ts: float, beta_params: Dict[str, float]) -> None:
        """Decays accumulators in O(1) time up to current_ts."""
        dt = current_ts - self.last_update_ts
        if dt <= 0.0:
            return
        for cat, val in list(self.accumulators.items()):
            beta = beta_params.get(cat, 0.05)
            decayed = val * math.exp(-beta * dt)
            if decayed < 1e-7:
                self.accumulators[cat] = 0.0
            else:
                self.accumulators[cat] = decayed
        self.last_update_ts = current_ts

    def add_excitation(self, category: str, alpha: float, magnitude: float = 1.0) -> None:
        """Adds instantaneous excitation to category."""
        prev = self.accumulators.get(category, 0.0)
        self.accumulators[category] = prev + (alpha * magnitude)
        self.event_count += 1


@dataclass
class HawkesIncidentEvent:
    event_id: str
    timestamp: float
    lat: float
    lon: float
    category: str
    severity: float = 1.0


class MarkovianH3HawkesEngine:
    """
    Carrier-Grade Spatio-Temporal Point Process with O(1) Time-Space Complexity.
    Replaces O(N) historical summation with exact Markovian state accumulators
    on an axial hexagonal spatial mesh.
    """

    CATEGORIES = ("FIRE", "MEDICAL", "HAZMAT", "POLICE", "INFRASTRUCTURE")

    def __init__(
        self,
        hex_radius_meters: float = 250.0,
        ref_lat: float = 37.7749,
        ref_lon: float = -122.4194,
        center_spatial_weight: float = 0.70,
        neighbor_spatial_weight: float = 0.05,
    ):
        self.projector = HexGridProjector(hex_radius_meters, ref_lat, ref_lon)
        self.w_center = center_spatial_weight
        self.w_neighbor = neighbor_spatial_weight
        self.lock = threading.RLock()

        # Baseline arrival rates mu_{c} (incidents/second)
        self.mu: Dict[str, float] = {
            "FIRE": 0.002,
            "MEDICAL": 0.008,
            "HAZMAT": 0.0005,
            "POLICE": 0.005,
            "INFRASTRUCTURE": 0.001,
        }

        # Self-excitation jump amplitude alpha_{c}
        self.alpha: Dict[str, float] = {
            "FIRE": 0.45,
            "MEDICAL": 0.35,
            "HAZMAT": 0.60,
            "POLICE": 0.40,
            "INFRASTRUCTURE": 0.50,
        }

        # Temporal decay rates beta_{c} (1/second)
        self.beta: Dict[str, float] = {
            "FIRE": 0.010,       # Half-life ~69.3s
            "MEDICAL": 0.015,    # Half-life ~46.2s
            "HAZMAT": 0.005,     # Half-life ~138.6s
            "POLICE": 0.020,     # Half-life ~34.6s
            "INFRASTRUCTURE": 0.008,
        }

        # Cross-category excitation coupling matrix M[target_cat][source_cat]
        self.cross_coupling: Dict[str, Dict[str, float]] = {
            "FIRE": {"FIRE": 1.0, "HAZMAT": 0.4, "INFRASTRUCTURE": 0.3, "MEDICAL": 0.1, "POLICE": 0.05},
            "MEDICAL": {"MEDICAL": 1.0, "FIRE": 0.5, "HAZMAT": 0.4, "POLICE": 0.3, "INFRASTRUCTURE": 0.1},
            "HAZMAT": {"HAZMAT": 1.0, "FIRE": 0.3, "INFRASTRUCTURE": 0.4, "MEDICAL": 0.05, "POLICE": 0.05},
            "POLICE": {"POLICE": 1.0, "FIRE": 0.2, "MEDICAL": 0.2, "HAZMAT": 0.2, "INFRASTRUCTURE": 0.1},
            "INFRASTRUCTURE": {"INFRASTRUCTURE": 1.0, "FIRE": 0.35, "HAZMAT": 0.35, "POLICE": 0.1, "MEDICAL": 0.05},
        }

        # Active hexagonal cells state store
        self.cells: Dict[str, HexCellState] = {}
        self.last_evaporation_ts: float = time.time()

    def _get_or_create_cell(self, hex_coord: HexCoord, current_ts: float) -> HexCellState:
        key = hex_coord.to_key()
        if key not in self.cells:
            self.cells[key] = HexCellState(
                hex_coord=hex_coord,
                last_update_ts=current_ts,
                accumulators={cat: 0.0 for cat in self.CATEGORIES},
            )
        return self.cells[key]

    def ingest_event(self, event: HawkesIncidentEvent) -> HexCoord:
        """
        Ingests an incident event into the hexagonal mesh in exact O(1) time.
        Updates state accumulators and advances the local cell timeline.
        """
        with self.lock:
            x, y = self.projector.lat_lon_to_xy(event.lat, event.lon)
            hex_coord = self.projector.xy_to_hex(x, y)
            cell = self._get_or_create_cell(hex_coord, event.timestamp)

            # O(1) decay before impulse addition
            cell.decay_to(event.timestamp, self.beta)

            # Add impulse
            cat = event.category.upper()
            alpha_val = self.alpha.get(cat, 0.4)
            cell.add_excitation(cat, alpha_val, event.severity)

            # Housekeeping: periodically evaporate dead cells every 300 seconds
            if event.timestamp - self.last_evaporation_ts > 300.0:
                self.evaporate_inactive_cells(event.timestamp)
                self.last_evaporation_ts = event.timestamp

            return hex_coord

    def query_intensity(
        self,
        lat: float,
        lon: float,
        category: str,
        current_ts: float,
    ) -> float:
        """
        Computes conditional intensity lambda_c(t, x) in guaranteed O(1) time.
        Scans exactly 1 center hex + 6 1-ring neighbors = 7 cells total.
        """
        with self.lock:
            cat = category.upper()
            base_rate = self.mu.get(cat, 0.005)

            x, y = self.projector.lat_lon_to_xy(lat, lon)
            center_hex = self.projector.xy_to_hex(x, y)

            total_excitation = 0.0

            # 1. Center cell contribution (weight = w_center)
            center_key = center_hex.to_key()
            if center_key in self.cells:
                c_cell = self.cells[center_key]
                c_cell.decay_to(current_ts, self.beta)
                cell_sum = 0.0
                coupling = self.cross_coupling.get(cat, {cat: 1.0})
                for src_cat, coupling_coeff in coupling.items():
                    cell_sum += coupling_coeff * c_cell.accumulators.get(src_cat, 0.0)
                total_excitation += self.w_center * cell_sum

            # 2. 6 1-ring neighbors contribution (weight = w_neighbor each)
            neighbors = center_hex.neighbors()
            for n_hex in neighbors:
                n_key = n_hex.to_key()
                if n_key in self.cells:
                    n_cell = self.cells[n_key]
                    n_cell.decay_to(current_ts, self.beta)
                    cell_sum = 0.0
                    coupling = self.cross_coupling.get(cat, {cat: 1.0})
                    for src_cat, coupling_coeff in coupling.items():
                        cell_sum += coupling_coeff * n_cell.accumulators.get(src_cat, 0.0)
                    total_excitation += self.w_neighbor * cell_sum

            return float(base_rate + total_excitation)

    def forecast_aftershocks(
        self,
        hex_coord: HexCoord,
        category: str,
        horizon_seconds: float = 3600.0,
        current_ts: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Integrates conditional intensity over time window [t, t + horizon]
        to compute expected number of triggered aftershocks (E[N] = integral lambda dt).
        """
        now = current_ts if current_ts is not None else time.time()
        with self.lock:
            cat = category.upper()
            mu_val = self.mu.get(cat, 0.005)
            beta_val = self.beta.get(cat, 0.01)

            # Poisson background expectation
            expected_background = mu_val * horizon_seconds

            # Triggered excitation expectation:
            # int_0^H A_0 * e^(-beta * t) dt = A_0 * (1 - e^(-beta * H)) / beta
            cell_key = hex_coord.to_key()
            accum_val = 0.0
            if cell_key in self.cells:
                cell = self.cells[cell_key]
                cell.decay_to(now, self.beta)
                accum_val = cell.accumulators.get(cat, 0.0)

            decay_integral = (1.0 - math.exp(-beta_val * horizon_seconds)) / beta_val if beta_val > 0 else horizon_seconds
            expected_triggered = accum_val * decay_integral

            total_expected = expected_background + (self.w_center * expected_triggered)
            # Branching ratio
            alpha_val = self.alpha.get(cat, 0.4)
            branching_ratio = alpha_val / beta_val if beta_val > 0 else 0.5
            is_supercritical = branching_ratio >= 1.0

            return {
                "hex_key": cell_key,
                "category": cat,
                "horizon_seconds": horizon_seconds,
                "expected_total_events": round(total_expected, 4),
                "expected_background_events": round(expected_background, 4),
                "expected_triggered_events": round(self.w_center * expected_triggered, 4),
                "branching_ratio": round(branching_ratio, 4),
                "is_supercritical": is_supercritical,
                "surge_risk_score": min(1.0, round(total_expected / (expected_background + 1.0), 3)),
            }

    def simulate_next_event_time(
        self,
        lat: float,
        lon: float,
        category: str,
        current_ts: float,
        max_horizon_seconds: float = 600.0,
    ) -> Optional[float]:
        """
        Uses Ogata's Modified Thinning Algorithm in O(1) time
        to simulate exact arrival time of next event in the local hex neighborhood.
        """
        cat = category.upper()
        t = current_ts
        lambda_bar = self.query_intensity(lat, lon, cat, t) * 1.5  # Upper bound candidate

        # Safety bound: at least 0.01 to prevent infinite loop
        if lambda_bar <= 0:
            lambda_bar = 0.01

        steps = 0
        while t < current_ts + max_horizon_seconds and steps < 200:
            steps += 1
            # Step 1: Draw exponential inter-arrival with rate lambda_bar
            u = 0.54321  # Deterministic pseudo-random seed or math.sin step
            # Generate deterministic quasi-random number based on time state
            pseudo_rand = ((math.sin(t * 123.456 + steps * 78.9) + 1.0) / 2.0)
            pseudo_rand = max(1e-5, min(0.99999, pseudo_rand))
            delta_t = -math.log(pseudo_rand) / lambda_bar
            t += delta_t

            if t > current_ts + max_horizon_seconds:
                return None

            # Step 2: Evaluate exact intensity at candidate time t
            lambda_cand = self.query_intensity(lat, lon, cat, t)
            accept_prob = lambda_cand / lambda_bar

            pseudo_rand_accept = ((math.cos(t * 456.789 + steps * 12.3) + 1.0) / 2.0)
            if pseudo_rand_accept <= accept_prob:
                return t  # Accepted candidate event

            # Update upper bound
            lambda_bar = max(lambda_cand * 1.2, self.mu.get(cat, 0.005))

        return None

    def export_geojson_heatmap(self, current_ts: Optional[float] = None) -> Dict[str, Any]:
        """
        Exports active hexagonal cells as a GeoJSON FeatureCollection
        for high-performance Cockpit GPU vector rendering.
        """
        now = current_ts if current_ts is not None else time.time()
        features: List[Dict[str, Any]] = []

        with self.lock:
            for key, cell in self.cells.items():
                cell.decay_to(now, self.beta)
                # Compute composite urgency intensity across categories
                composite_intensity = sum(cell.accumulators.values())
                if composite_intensity < 0.005 and cell.event_count == 0:
                    continue

                lat_lon_poly = self.projector.hex_to_polygon_lat_lon(cell.hex_coord)
                # GeoJSON coordinates format: [lon, lat]
                geojson_poly = [[lon, lat] for lat, lon in lat_lon_poly]

                features.append({
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [geojson_poly]
                    },
                    "properties": {
                        "hex_id": key,
                        "q": cell.hex_coord.q,
                        "r": cell.hex_coord.r,
                        "composite_intensity": round(composite_intensity, 4),
                        "event_count": cell.event_count,
                        "categories": {cat: round(val, 4) for cat, val in cell.accumulators.items()},
                        "last_update_ts": cell.last_update_ts,
                    }
                })

        return {
            "type": "FeatureCollection",
            "features": features,
            "metadata": {
                "generated_at": now,
                "active_hex_count": len(features),
                "grid_radius_meters": self.projector.r_hex,
            }
        }

    def evaporate_inactive_cells(self, current_ts: float) -> int:
        """Removes cells whose accumulators have completely evaporated."""
        evaporated_keys: List[str] = []
        for key, cell in self.cells.items():
            cell.decay_to(current_ts, self.beta)
            if sum(cell.accumulators.values()) < 1e-6:
                evaporated_keys.append(key)
        for k in evaporated_keys:
            del self.cells[k]
        return len(evaporated_keys)
