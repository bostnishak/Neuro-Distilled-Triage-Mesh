import math
from dataclasses import dataclass
from typing import List, Optional, Tuple
from domain.value_objects import GeoCoordinates


@dataclass(frozen=True)
class HawkesHistoricalEvent:
    timestamp_seconds: float
    location: GeoCoordinates
    magnitude: float = 1.0


@dataclass(frozen=True)
class HawkesParameters:
    mu: float = 0.005       # Background Poisson rate (events / sec)
    alpha: float = 0.45     # Excitation magnitude parameter
    beta: float = 0.002     # Temporal decay rate (1/sec) -> ~500 sec half-life
    sigma_meters: float = 400.0  # Spatial dispersion radius in meters

    @property
    def branching_ratio(self) -> float:
        """Branching ratio eta = alpha / beta. System is stable iff eta < 1.0."""
        return self.alpha / self.beta if self.beta > 0 else 0.0

    @property
    def is_subcritical(self) -> bool:
        return self.branching_ratio < 1.0


class HawkesProcessEngine:
    """Mathematical Spatio-Temporal Hawkes Self-Exciting Point Process Engine."""

    def __init__(self, params: Optional[HawkesParameters] = None):
        self.params = params or HawkesParameters()

    def spatial_kernel(self, dist_meters: float) -> float:
        """Evaluates 2D Gaussian spatial kernel: (1 / (2*pi*sigma^2)) * exp(-dist^2 / (2*sigma^2))."""
        sigma = self.params.sigma_meters
        variance = sigma * sigma
        norm_const = 1.0 / (2.0 * math.pi * variance)
        exponent = - (dist_meters * dist_meters) / (2.0 * variance)
        return norm_const * math.exp(exponent)

    def temporal_decay(self, delta_t_seconds: float) -> float:
        """Evaluates exponential temporal decay kernel: exp(-beta * delta_t)."""
        if delta_t_seconds < 0:
            return 0.0
        return math.exp(-self.params.beta * delta_t_seconds)

    def conditional_intensity(
        self,
        current_time_sec: float,
        target_location: GeoCoordinates,
        history: List[HawkesHistoricalEvent],
    ) -> float:
        """Computes conditional intensity lambda(t, x, y) = mu + sum_{t_i < t} alpha * g(t - t_i) * f(x - x_i)."""
        intensity = self.params.mu

        for event in history:
            delta_t = current_time_sec - event.timestamp_seconds
            if delta_t <= 0:
                continue

            dist = target_location.haversine_distance_meters(event.location)
            # Spatio-temporal self-excitation
            temporal = self.temporal_decay(delta_t)
            spatial = self.spatial_kernel(dist)

            excitation = self.params.alpha * event.magnitude * temporal * spatial
            intensity += excitation

        return intensity

    def compute_aftershock_probability(
        self,
        current_time_sec: float,
        target_location: GeoCoordinates,
        history: List[HawkesHistoricalEvent],
        horizon_seconds: float = 3600.0,
    ) -> float:
        """Estimates probability of >= 1 aftershock within horizon [t, t + horizon_seconds].

        P(N >= 1) = 1 - exp(-Integral_{t}^{t+T} lambda(tau) dtau).
        """
        # Baseline integral
        base_integral = self.params.mu * horizon_seconds

        # Excitation integral for each past event
        excitation_integral = 0.0
        for event in history:
            delta_t = current_time_sec - event.timestamp_seconds
            if delta_t < 0:
                continue

            dist = target_location.haversine_distance_meters(event.location)
            spatial = self.spatial_kernel(dist)

            # Integral of exp(-beta * (t_future - t_i)) dt_future from t to t + T:
            # = (exp(-beta * delta_t) - exp(-beta * (delta_t + T))) / beta
            exp_start = math.exp(-self.params.beta * delta_t)
            exp_end = math.exp(-self.params.beta * (delta_t + horizon_seconds))
            time_int = (exp_start - exp_end) / self.params.beta if self.params.beta > 0 else horizon_seconds

            excitation_integral += self.params.alpha * event.magnitude * spatial * time_int

        total_compensator = base_integral + excitation_integral
        prob = 1.0 - math.exp(-total_compensator)
        return min(max(prob, 0.0), 1.0)

    def evaluate_deduplication_ratio(
        self,
        current_time_sec: float,
        new_location: GeoCoordinates,
        cluster_history: List[HawkesHistoricalEvent],
    ) -> Tuple[bool, float]:
        """Calculates ratio of cluster excitation vs background noise.

        If excitation / total_intensity > threshold (e.g. 0.70), incident is classified as a duplicate/aftershock.
        Returns (is_duplicate_aftershock, excitation_ratio).
        """
        if not cluster_history:
            return False, 0.0

        total_lambda = self.conditional_intensity(current_time_sec, new_location, cluster_history)
        excitation_part = max(0.0, total_lambda - self.params.mu)

        ratio = excitation_part / total_lambda if total_lambda > 0 else 0.0
        is_dedup = ratio >= 0.65
        return is_dedup, ratio

    @staticmethod
    def update_cluster_centroid(
        current_centroid: GeoCoordinates,
        current_count: int,
        new_location: GeoCoordinates,
    ) -> Tuple[GeoCoordinates, float]:
        """Incremental online center-of-mass update for spatial cluster and radius."""
        new_count = current_count + 1
        new_lat = ((current_centroid.latitude * current_count) + new_location.latitude) / new_count
        new_lon = ((current_centroid.longitude * current_count) + new_location.longitude) / new_count
        updated_centroid = GeoCoordinates(latitude=new_lat, longitude=new_lon)

        dist_to_new = updated_centroid.haversine_distance_meters(new_location)
        # Dynamic cluster radius covers 95% dispersion
        new_radius = max(350.0, dist_to_new * 1.5)
        return updated_centroid, new_radius
