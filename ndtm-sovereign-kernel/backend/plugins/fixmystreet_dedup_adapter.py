from typing import Any, Dict
from sdk.interfaces import DatasetAdapter


class FixMyStreetCivicAdapter(DatasetAdapter):
    """Adapter for FixMyStreet and Open311 municipal civic incident feeds."""

    @property
    def source_identifier(self) -> str:
        return "fixmystreet_open311"

    def parse_payload(self, raw_input: Dict[str, Any]) -> Dict[str, Any]:
        """Translates Open311 / FixMyStreet JSON format into NDTM schema."""
        raw_service_name = str(raw_input.get("service_name", "Municipal Issue")).strip()
        description = str(raw_input.get("description", raw_input.get("detail", ""))).strip()

        # Map external service names to internal categories
        category_map = {
            "pothole": "ROAD_HAZARD",
            "street light": "ELECTRICAL_GRID",
            "water leak": "WATER_MAINS",
            "gas leak": "GAS_PIPELINE",
            "structural crack": "STRUCTURAL_COLLAPSE",
            "fire": "INDUSTRIAL_FIRE",
        }

        matched_category = "CIVIL_DEFENSE"
        for key, val in category_map.items():
            if key in raw_service_name.lower() or key in description.lower():
                matched_category = val
                break

        # Map priority/urgency
        external_urgency = str(raw_input.get("urgency", "MEDIUM")).upper()
        if external_urgency in {"CRITICAL", "HIGH", "MEDIUM", "LOW"}:
            urgency = external_urgency
        elif "danger" in description.lower() or "emergency" in description.lower():
            urgency = "HIGH"
        else:
            urgency = "MEDIUM"

        lat = float(raw_input.get("lat", raw_input.get("latitude", 41.0082)))
        lon = float(raw_input.get("long", raw_input.get("longitude", 28.9784)))

        return {
            "title": f"Civic: {raw_service_name}",
            "description": description,
            "category": matched_category,
            "urgency": urgency,
            "modality": "TEXT_OPTICAL" if raw_input.get("media_url") else "TEXT_ONLY",
            "latitude": lat,
            "longitude": lon,
            "address": raw_input.get("address_string", "Istanbul Urban Core"),
            "source_protocol": self.source_identifier,
            "metadata_json": {
                "service_request_id": raw_input.get("service_request_id"),
                "agency_responsible": raw_input.get("agency_responsible"),
                "media_url": raw_input.get("media_url"),
            },
        }

    def validate_schema(self, parsed_payload: Dict[str, Any]) -> bool:
        """Validates that parsed payload satisfies mandatory fields."""
        required = ["title", "description", "category", "urgency", "latitude", "longitude"]
        for field in required:
            if field not in parsed_payload or parsed_payload[field] is None:
                return False
        if not (-90.0 <= parsed_payload["latitude"] <= 90.0):
            return False
        if not (-180.0 <= parsed_payload["longitude"] <= 180.0):
            return False
        return True
