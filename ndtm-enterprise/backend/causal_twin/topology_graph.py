"""Causal Digital Twin Graph Representation & Structural Equation Model (SEM).
Implements directed acyclic graph topology representing 12 Istanbul metro
critical infrastructure nodes and 18 coupling edges.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class NodeDefinition:
    node_code: str
    node_type: str
    latitude: float
    longitude: float
    base_failure_prob: float
    current_health_score: float
    capacity_kw: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class EdgeDefinition:
    source_code: str
    target_code: str
    dependency_weight: float
    propagation_delay_minutes: int
    coupling_type: str


# Canonical 12 Nodes across Istanbul
ISTANBUL_INFRASTRUCTURE_NODES: list[NodeDefinition] = [
    NodeDefinition("SUBSTATION_IKITELLI", "SUBSTATION", 41.0768, 28.7952, 0.015, 98.5, 120000.0, {"voltage_kv": 380, "region": "Avrupa-1", "operator": "TEIAS"}),
    NodeDefinition("SUBSTATION_KADIKOY", "SUBSTATION", 40.9901, 29.0298, 0.012, 99.1, 85000.0, {"voltage_kv": 154, "region": "Anadolu-1", "operator": "AYEDAS"}),
    NodeDefinition("SUBSTATION_LEVENT", "SUBSTATION", 41.0825, 29.0125, 0.008, 99.8, 95000.0, {"voltage_kv": 154, "region": "Finans-Merkezi", "operator": "BEDAS"}),
    NodeDefinition("SUBSTATION_UMRANIYE", "SUBSTATION", 41.0255, 29.1190, 0.010, 97.4, 75000.0, {"voltage_kv": 154, "region": "Anadolu-2", "operator": "AYEDAS"}),
    NodeDefinition("FIBER_BOGAZICI_NORTH", "FIBER_BACKBONE", 41.0850, 29.0550, 0.005, 100.0, 10000.0, {"bandwidth_tbps": 80, "submarine_crossing": True}),
    NodeDefinition("FIBER_MARMARAY_CORE", "FIBER_BACKBONE", 41.0122, 28.9875, 0.004, 100.0, 12000.0, {"bandwidth_tbps": 120, "tunnel_embedded": True}),
    NodeDefinition("CELL_TOWER_CAMLICA", "CELL_TOWER", 41.0280, 29.0680, 0.020, 96.0, 350.0, {"antennas": 16, "5g_standalone": True}),
    NodeDefinition("CELL_TOWER_MASLAK", "CELL_TOWER", 41.1105, 29.0210, 0.018, 97.5, 280.0, {"antennas": 12, "5g_standalone": True}),
    NodeDefinition("WATER_PUMP_TERKOS", "WATER_PUMP", 41.3320, 28.6750, 0.025, 94.0, 45000.0, {"flow_m3_sec": 12.5, "backup_generator": True}),
    NodeDefinition("WATER_PUMP_OMERLI", "WATER_PUMP", 41.0450, 29.3550, 0.022, 95.5, 55000.0, {"flow_m3_sec": 18.0, "backup_generator": True}),
    NodeDefinition("FACTORY_FURNACE_DUDULLU", "FACTORY_FURNACE", 41.0110, 29.1550, 0.030, 91.0, 60000.0, {"temp_celsius": 1450, "safety_interlock": True}),
    NodeDefinition("FACTORY_FURNACE_TUZLA", "FACTORY_FURNACE", 40.8550, 29.3100, 0.028, 92.5, 72000.0, {"temp_celsius": 1520, "safety_interlock": True}),
]

# Canonical 18 Directed Coupling Edges
ISTANBUL_INFRASTRUCTURE_EDGES: list[EdgeDefinition] = [
    EdgeDefinition("SUBSTATION_IKITELLI", "WATER_PUMP_TERKOS", 0.95, 5, "POWER_FEED"),
    EdgeDefinition("SUBSTATION_IKITELLI", "FIBER_BOGAZICI_NORTH", 0.85, 10, "POWER_FEED"),
    EdgeDefinition("SUBSTATION_LEVENT", "CELL_TOWER_MASLAK", 0.90, 8, "POWER_FEED"),
    EdgeDefinition("SUBSTATION_LEVENT", "FIBER_BOGAZICI_NORTH", 0.75, 15, "POWER_FEED"),
    EdgeDefinition("SUBSTATION_KADIKOY", "FIBER_MARMARAY_CORE", 0.92, 5, "POWER_FEED"),
    EdgeDefinition("SUBSTATION_KADIKOY", "CELL_TOWER_CAMLICA", 0.88, 12, "POWER_FEED"),
    EdgeDefinition("SUBSTATION_UMRANIYE", "WATER_PUMP_OMERLI", 0.94, 6, "POWER_FEED"),
    EdgeDefinition("SUBSTATION_UMRANIYE", "FACTORY_FURNACE_DUDULLU", 0.89, 7, "POWER_FEED"),
    EdgeDefinition("SUBSTATION_UMRANIYE", "FACTORY_FURNACE_TUZLA", 0.82, 18, "POWER_FEED"),
    EdgeDefinition("FIBER_BOGAZICI_NORTH", "CELL_TOWER_MASLAK", 0.80, 2, "TELECOM_BACKHAUL"),
    EdgeDefinition("FIBER_MARMARAY_CORE", "CELL_TOWER_CAMLICA", 0.85, 3, "TELECOM_BACKHAUL"),
    EdgeDefinition("FIBER_BOGAZICI_NORTH", "FIBER_MARMARAY_CORE", 0.70, 1, "TELECOM_BACKHAUL"),
    EdgeDefinition("CELL_TOWER_MASLAK", "SUBSTATION_LEVENT", 0.65, 5, "TELECOM_BACKHAUL"),
    EdgeDefinition("CELL_TOWER_CAMLICA", "SUBSTATION_UMRANIYE", 0.60, 5, "TELECOM_BACKHAUL"),
    EdgeDefinition("WATER_PUMP_TERKOS", "SUBSTATION_IKITELLI", 0.78, 25, "COOLING_SUPPLY"),
    EdgeDefinition("WATER_PUMP_OMERLI", "FACTORY_FURNACE_DUDULLU", 0.88, 20, "COOLING_SUPPLY"),
    EdgeDefinition("WATER_PUMP_OMERLI", "FACTORY_FURNACE_TUZLA", 0.91, 30, "COOLING_SUPPLY"),
    EdgeDefinition("WATER_PUMP_TERKOS", "SUBSTATION_LEVENT", 0.68, 35, "COOLING_SUPPLY"),
]


class CausalTopologyGraph:
    """Directed graph topology with structural adjacency and path evaluation."""

    def __init__(
        self,
        nodes: list[NodeDefinition] | None = None,
        edges: list[EdgeDefinition] | None = None,
    ) -> None:
        self.nodes = {n.node_code: n for n in (nodes or ISTANBUL_INFRASTRUCTURE_NODES)}
        self.edges = edges or list(ISTANBUL_INFRASTRUCTURE_EDGES)
        self.adj_out: dict[str, list[EdgeDefinition]] = {k: [] for k in self.nodes}
        self.adj_in: dict[str, list[EdgeDefinition]] = {k: [] for k in self.nodes}

        for edge in self.edges:
            if edge.source_code in self.adj_out:
                self.adj_out[edge.source_code].append(edge)
            if edge.target_code in self.adj_in:
                self.adj_in[edge.target_code].append(edge)

    def get_node(self, node_code: str) -> NodeDefinition | None:
        return self.nodes.get(node_code)

    def get_outgoing_edges(self, node_code: str) -> list[EdgeDefinition]:
        return self.adj_out.get(node_code, [])

    def get_incoming_edges(self, node_code: str) -> list[EdgeDefinition]:
        return self.adj_in.get(node_code, [])

    def clone_mutilated(self, severed_target_node: str) -> CausalTopologyGraph:
        """Constructs Pearl's mutilated graph G_{X-bar} with all incoming edges to severed_target_node removed."""
        filtered_edges = [
            e for e in self.edges if e.target_code != severed_target_node
        ]
        return CausalTopologyGraph(list(self.nodes.values()), filtered_edges)
