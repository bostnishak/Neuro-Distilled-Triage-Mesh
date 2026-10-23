"""Domain taxonomy — single source of truth for labels.

Shared by the distillation pipeline (training targets), the ONNX student
(output decoding), the teacher prompts and the semantic router.
Changing this file requires re-training the student model.
"""
from __future__ import annotations

from typing import Final

INTENT_DESCRIPTIONS: Final[dict[str, str]] = {
    "road_damage": "Potholes, cracks, sinkholes or damaged pavement/sidewalks.",
    "water_leak": "Burst pipes, water main leaks, sewage overflow, flooding from infrastructure.",
    "power_outage": "Loss of electricity, damaged transformers, downed power lines.",
    "streetlight_failure": "Broken, flickering or permanently-on street lights.",
    "waste_management": "Uncollected garbage, illegal dumping, overflowing bins.",
    "public_safety_hazard": "Fallen trees, exposed wires, gas smells, collapsing structures, fire risk.",
    "traffic_signal_failure": "Malfunctioning or dark traffic lights and pedestrian signals.",
    "it_service_request": "Technical/IT tickets: accounts, network, VPN, hardware, software.",
    "other": "Anything that does not clearly fit the categories above.",
}

INTENTS: Final[tuple[str, ...]] = tuple(INTENT_DESCRIPTIONS.keys())
FALLBACK_INTENT: Final[str] = "other"

ENTITY_TYPES: Final[tuple[str, ...]] = ("LOCATION", "ASSET", "HAZARD")
BIO_LABELS: Final[tuple[str, ...]] = ("O", *[f"{p}-{t}" for t in ENTITY_TYPES for p in ("B", "I")])


def urgency_to_priority(urgency: float) -> int:
    """Map an urgency score in [0, 1] to a priority level P1 (critical) .. P4 (low)."""
    if urgency >= 0.85:
        return 1
    if urgency >= 0.60:
        return 2
    if urgency >= 0.35:
        return 3
    return 4
