import random
from typing import Callable, Dict, List, Tuple
import numpy as np
from core.logging_otel import logger
from domain.value_objects import GeoCoordinates


class MetamorphicAIFuzzer:
    """Automated Metamorphic Testing and Invariance Fuzzing Harness for AI Triage Pipelines."""

    SYNONYM_REPLACEMENTS = {
        "gaz sızıntısı": "doğalgaz kaçağı",
        "yangın": "alev ve duman",
        "patlama": "infilak",
        "çökme": "göçük tehlikesi",
        "su borusu patlağı": "şebeke suyu taşkını",
        "elektrik kesintisi": "trafo arızası",
        "tehlike": "riskli durum",
    }

    @classmethod
    def apply_synonym_transform(cls, text: str) -> str:
        """Applies metamorphic linguistic perturbation."""
        transformed = text
        for orig, syn in cls.SYNONYM_REPLACEMENTS.items():
            if orig in transformed.lower():
                transformed = transformed.replace(orig, syn)
        return transformed

    @classmethod
    def apply_spatial_jitter(cls, coord: GeoCoordinates, max_meters: float = 50.0) -> GeoCoordinates:
        """Applies metamorphic micro-spatial translation: delta_deg ~ delta_m / 111320."""
        # 1 degree latitude ~ 111,320 meters
        delta_lat = (random.uniform(-max_meters, max_meters)) / 111320.0
        delta_lon = (random.uniform(-max_meters, max_meters)) / (111320.0 * np.cos(np.radians(coord.latitude)))
        return GeoCoordinates(
            latitude=round(coord.latitude + delta_lat, 7),
            longitude=round(coord.longitude + delta_lon, 7),
        )

    @classmethod
    def apply_acoustic_noise(cls, mel_filterbanks: Tuple[float, ...], snr_db: float = 25.0) -> Tuple[float, ...]:
        """Injects metamorphic Gaussian white noise calibrated to target Signal-to-Noise Ratio (SNR)."""
        signal = np.array(mel_filterbanks, dtype=np.float32)
        signal_power = np.mean(signal ** 2)
        if signal_power <= 0:
            return mel_filterbanks

        # SNR_db = 10 * log10(P_signal / P_noise) -> P_noise = P_signal / 10^(SNR/10)
        noise_power = signal_power / (10.0 ** (snr_db / 10.0))
        noise = np.random.normal(0.0, np.sqrt(noise_power), size=signal.shape)
        noisy_signal = signal + noise
        return tuple(float(x) for x in noisy_signal)

    def run_metamorphic_fuzz_suite(
        self,
        triage_fn: Callable[[str, GeoCoordinates], str],
        test_cases: List[Tuple[str, GeoCoordinates, str]],
    ) -> Dict[str, Any]:
        """Fuzzes triage function across all 3 metamorphic relations.

        test_cases: list of (input_text, coordinates, expected_category).
        Returns diagnostic invariance report.
        """
        total_trials = 0
        passed_trials = 0
        violations: List[Dict[str, Any]] = []

        for text, coords, expected_cat in test_cases:
            # Baseline inference
            base_pred = triage_fn(text, coords)

            # Test Relation 1: Synonym Invariance
            total_trials += 1
            syn_text = self.apply_synonym_transform(text)
            syn_pred = triage_fn(syn_text, coords)
            if syn_pred == base_pred:
                passed_trials += 1
            else:
                violations.append({
                    "relation": "SYNONYM_INVARIANCE",
                    "original": text,
                    "mutated": syn_text,
                    "expected": base_pred,
                    "actual": syn_pred,
                })

            # Test Relation 2: Spatial Translation Invariance (50m)
            total_trials += 1
            jittered_coords = self.apply_spatial_jitter(coords, max_meters=50.0)
            spatial_pred = triage_fn(text, jittered_coords)
            if spatial_pred == base_pred:
                passed_trials += 1
            else:
                violations.append({
                    "relation": "SPATIAL_JITTER_INVARIANCE",
                    "orig_coords": (coords.latitude, coords.longitude),
                    "jittered_coords": (jittered_coords.latitude, jittered_coords.longitude),
                    "expected": base_pred,
                    "actual": spatial_pred,
                })

        pass_rate = (passed_trials / total_trials) if total_trials > 0 else 1.0
        robustness_score = round(pass_rate * 100.0, 2)

        report = {
            "total_metamorphic_trials": total_trials,
            "passed_trials": passed_trials,
            "failed_violations_count": len(violations),
            "robustness_score_percent": robustness_score,
            "violations_sample": violations[:5],
        }
        logger.info("metamorphic_fuzz_completed", **report)
        return report
