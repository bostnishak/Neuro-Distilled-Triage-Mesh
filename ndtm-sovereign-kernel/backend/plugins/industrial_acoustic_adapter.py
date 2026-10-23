from typing import Any, Dict, List
from sdk.interfaces import DatasetAdapter


class IndustrialAcousticAdapter(DatasetAdapter):
    """Adapter for SCADA acoustic microphones, turbine vibration monitors, and pipeline pressure hydrophones."""

    @property
    def source_identifier(self) -> str:
        return "industrial_acoustic_scada"

    def parse_payload(self, raw_input: Dict[str, Any]) -> Dict[str, Any]:
        """Translates SCADA acoustic telemetry into standardized incident representation."""
        sensor_id = str(raw_input.get("sensor_id", "SENSOR_UNKNOWN"))
        decibel_level = float(raw_input.get("db_level", 0.0))
        frequency_dominant = float(raw_input.get("dominant_hz", 0.0))
        anomaly_score = float(raw_input.get("acoustic_anomaly_score", 0.0))

        # Infer category and urgency based on acoustic thresholds
        if decibel_level > 115.0 or anomaly_score > 0.85:
            urgency = "CRITICAL"
            category = "GAS_PIPELINE" if "pipeline" in sensor_id.lower() else "INDUSTRIAL_FIRE"
        elif decibel_level > 90.0 or anomaly_score > 0.60:
            urgency = "HIGH"
            category = "ELECTRICAL_GRID"
        else:
            urgency = "MEDIUM"
            category = "HAZMAT_LEAK"

        lat = float(raw_input.get("latitude", 41.0151))
        lon = float(raw_input.get("longitude", 28.9795))

        # Mel filterbanks if provided by sensor DSP
        filterbanks = raw_input.get("filterbanks", [0.0] * 16)
        if len(filterbanks) != 16:
            filterbanks = [0.0] * 16

        return {
            "title": f"Acoustic Anomaly Alert: Sensor {sensor_id}",
            "description": (
                f"Automated acoustic alarm from sensor {sensor_id}. "
                f"Peak dB: {decibel_level:.1f}, Dominant Hz: {frequency_dominant:.1f}, "
                f"Anomaly Score: {anomaly_score:.3f}."
            ),
            "category": category,
            "urgency": urgency,
            "modality": "ACOUSTIC_ONLY",
            "latitude": lat,
            "longitude": lon,
            "address": f"SCADA Node {sensor_id} Zone",
            "source_protocol": self.source_identifier,
            "acoustic_data": {
                "energy_db": decibel_level,
                "spectral_entropy": anomaly_score,
                "filterbank_energies": filterbanks,
            },
            "metadata_json": {
                "sensor_id": sensor_id,
                "firmware_version": raw_input.get("firmware_version", "1.0.0"),
                "calibrated_at": raw_input.get("calibrated_at"),
            },
        }

    def validate_schema(self, parsed_payload: Dict[str, Any]) -> bool:
        """Validates that parsed payload satisfies mandatory fields."""
        required = ["title", "description", "category", "urgency", "latitude", "longitude"]
        for field in required:
            if field not in parsed_payload or parsed_payload[field] is None:
                return False
        return True
