from typing import Any, Dict, List, Optional, Protocol, runtime_checkable
from domain.entities import IncidentEntity
from domain.value_objects import GeoCoordinates, EmbeddingVector


@runtime_checkable
class DatasetAdapter(Protocol):
    """Protocol for external incident data source adapters."""

    @property
    def source_identifier(self) -> str:
        """Unique key for the data source (e.g., 'fixmystreet_v2', 'scada_water')."""
        ...

    def parse_payload(self, raw_input: Dict[str, Any]) -> Dict[str, Any]:
        """Translates third-party raw dictionary into standardized NDTM ingestion schema."""
        ...

    def validate_schema(self, parsed_payload: Dict[str, Any]) -> bool:
        """Ensures all mandatory fields (lat, lon, urgency, description) are valid."""
        ...


@runtime_checkable
class DSLRulePlugin(Protocol):
    """Protocol for dynamically injected business and safety validation rules."""

    @property
    def rule_name(self) -> str:
        ...

    @property
    def priority(self) -> int:
        ...

    def evaluate(self, incident: IncidentEntity, context: Dict[str, Any]) -> bool:
        """Evaluates rule against incident state. Returns True if condition is satisfied."""
        ...

    def apply_effect(self, incident: IncidentEntity, context: Dict[str, Any]) -> Dict[str, Any]:
        """Returns metadata mutations or actions triggered when rule condition holds."""
        ...


@runtime_checkable
class RoutingPolicyPlugin(Protocol):
    """Protocol for adaptive model and dispatch routing policies."""

    @property
    def policy_name(self) -> str:
        ...

    def should_escalate_to_teacher(
        self,
        student_entropy: float,
        ood_distance: float,
        modality: str,
        priority: str,
    ) -> bool:
        """Determines whether low-latency student inference must fall back to teacher LLM."""
        ...

    def calculate_dispatch_urgency_multiplier(
        self,
        incident: IncidentEntity,
        aftershock_intensity: float,
    ) -> float:
        """Calculates dynamic priority scalar for Z3 MaxSMT objective weights."""
        ...
