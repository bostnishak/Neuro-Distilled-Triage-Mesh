"""
Neuro-Distilled Triage Mesh (NDTM) — Sovereign Distributed & Failure-Proof Kernel
RFC-NDTM-OMEGA: Production Hardening Engine v3.0

Phase 28: Smith-Predictor PID Router
Filtered Derivative-on-Measurement, Anti-Windup Tracking, Dead-Time Delay Compensation,
and Schmitt-Trigger Hysteresis Router.
"""

from __future__ import annotations

import collections
import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Deque, Dict, List, Optional, Tuple


class RouteTarget(str, Enum):
    LOCAL_EDGE_SPSC = "LOCAL_EDGE_SPSC"
    REGIONAL_DISTILLED_SLM = "REGIONAL_DISTILLED_SLM"
    SOVEREIGN_CLOUD_TEACHER = "SOVEREIGN_CLOUD_TEACHER"


@dataclass
class PIDTelemetryRecord:
    timestamp: float
    setpoint: float
    measurement: float
    error: float
    p_term: float
    i_term: float
    d_term: float
    control_output_raw: float
    control_output_clamped: float
    smith_correction: float
    hysteresis_state: str
    target_tier: RouteTarget


class SmithPredictorPIDRouter:
    """
    Industrial Control-Theoretic Incident Routing Controller.
    
    1. Filtered Derivative on Measurement: D(s) = -Kd * s / (1 + alpha_d * Td * s) * Y(s).
       Prevents derivative spikes on sudden setpoint or batch arrivals.
    2. Tracking Anti-Windup Clamping: Freezes and discharges integrator during saturation.
    3. Smith Predictor Dead-Time Compensator: Cancels pipeline latency L (inference queue dead-time).
    4. Schmitt-Trigger Hysteresis: Eliminates high-frequency oscillation across tier boundaries.
    """

    def __init__(
        self,
        kp: float = 1.85,
        ki: float = 0.35,
        kd: float = 0.08,
        tau_filter: float = 0.02,       # Derivative low-pass filter time constant (alpha_d * Td)
        anti_windup_tracking: float = 0.5, # Tracking time constant 1/Tt
        u_min: float = 0.0,
        u_max: float = 1.0,
        # Smith Predictor Plant Model: Gp(s) = K_plant / (tau_plant * s + 1) * exp(-dead_time * s)
        k_plant: float = 1.0,
        tau_plant: float = 0.15,
        dead_time_seconds: float = 0.050,  # 50ms transport delay in edge inference queue
        # Schmitt-trigger hysteresis parameters
        threshold_low_to_mid: float = 0.40,
        threshold_mid_to_high: float = 0.75,
        hysteresis_delta: float = 0.025,
    ):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.tau_filter = max(1e-4, tau_filter)
        self.anti_windup_tracking = anti_windup_tracking
        self.u_min = u_min
        self.u_max = u_max

        # Plant model parameters
        self.k_plant = k_plant
        self.tau_plant = max(1e-4, tau_plant)
        self.dead_time = dead_time_seconds

        # Hysteresis parameters
        self.th_low_mid = threshold_low_to_mid
        self.th_mid_high = threshold_mid_to_high
        self.delta = hysteresis_delta

        # Controller state
        self.integrator: float = 0.0
        self.prev_measurement: float = 0.0
        self.prev_derivative: float = 0.0
        self.last_ts: Optional[float] = None

        # Smith Predictor Internal Simulator States
        self.sim_y_undelayed: float = 0.0
        # Ring buffer for simulating dead-time delay: deque of (sim_time, value)
        self.delay_buffer: Deque[Tuple[float, float]] = collections.deque()

        # Routing State Machine
        self.current_tier: RouteTarget = RouteTarget.LOCAL_EDGE_SPSC

        # Telemetry History (in-memory ring buffer)
        self.history: Deque[PIDTelemetryRecord] = collections.deque(maxlen=2000)

    def reset(self) -> None:
        """Resets all internal controller and plant simulation states."""
        self.integrator = 0.0
        self.prev_measurement = 0.0
        self.prev_derivative = 0.0
        self.last_ts = None
        self.sim_y_undelayed = 0.0
        self.delay_buffer.clear()
        self.current_tier = RouteTarget.LOCAL_EDGE_SPSC

    def _update_smith_plant(self, u_control: float, dt: float, current_ts: float) -> Tuple[float, float]:
        """
        Simulates first-order lag plant with dead time:
        dy_undelayed/dt = (k_plant * u - y_undelayed) / tau_plant
        """
        # Euler integration for undelayed model
        dy = (self.k_plant * u_control - self.sim_y_undelayed) / self.tau_plant
        self.sim_y_undelayed += dy * dt

        # Push to delay FIFO
        self.delay_buffer.append((current_ts, self.sim_y_undelayed))

        # Retrieve delayed value from history at (current_ts - dead_time)
        target_ts = current_ts - self.dead_time
        sim_y_delayed = self.sim_y_undelayed

        while len(self.delay_buffer) > 1 and self.delay_buffer[0][0] < target_ts:
            if self.delay_buffer[1][0] <= target_ts:
                self.delay_buffer.popleft()
            else:
                # Linear interpolation between buffer[0] and buffer[1]
                t0, v0 = self.delay_buffer[0]
                t1, v1 = self.delay_buffer[1]
                ratio = (target_ts - t0) / max(1e-6, t1 - t0)
                sim_y_delayed = v0 + ratio * (v1 - v0)
                break

        if len(self.delay_buffer) == 1:
            sim_y_delayed = self.delay_buffer[0][1]

        return self.sim_y_undelayed, sim_y_delayed

    def compute_step(
        self,
        setpoint: float,
        measurement: float,
        current_ts: Optional[float] = None,
    ) -> PIDTelemetryRecord:
        """
        Executes one discrete control cycle.
        
        Args:
            setpoint: Target latency or queue fill target (normalized 0.0 to 1.0).
            measurement: Current observed queue pressure or p99 latency metric.
            current_ts: Current unix epoch time in seconds.
        """
        now = current_ts if current_ts is not None else time.time()
        if self.last_ts is None:
            dt = 0.010  # Initial nominal step 10ms
        else:
            dt = max(1e-4, min(1.0, now - self.last_ts))
        self.last_ts = now

        # 1. Update Smith Predictor Plant Model using previous control signal
        prev_u = self.history[-1].control_output_clamped if self.history else 0.0
        y_sim_undelayed, y_sim_delayed = self._update_smith_plant(prev_u, dt, now)

        # Smith correction: (y_hat_undelayed - y_hat_delayed)
        smith_correction = y_sim_undelayed - y_sim_delayed

        # Predicted feedback signal fed to PID controller:
        # y_predicted = y_measured + smith_correction
        predicted_measurement = measurement + smith_correction

        # Error
        error = setpoint - predicted_measurement

        # 2. Proportional Term
        p_term = self.kp * error

        # 3. Filtered Derivative on Measurement (avoids derivative kick)
        # delta_y = measurement - prev_measurement
        delta_m = measurement - self.prev_measurement
        # First-order filtered derivative: D(k) = (tau / (tau + dt)) * D(k-1) - (Kd / (tau + dt)) * delta_m
        d_term = (self.tau_filter / (self.tau_filter + dt)) * self.prev_derivative - (self.kd / (self.tau_filter + dt)) * delta_m
        self.prev_derivative = d_term
        self.prev_measurement = measurement

        # 4. Provisional Raw Control Signal
        u_raw = p_term + self.integrator + d_term

        # 5. Saturation & Clamping
        u_clamped = max(self.u_min, min(self.u_max, u_raw))

        # 6. Integrator Anti-Windup Tracking Update
        # Integrator advances with error, and is corrected by (u_clamped - u_raw)
        sat_diff = u_clamped - u_raw
        self.integrator += (self.ki * error + self.anti_windup_tracking * sat_diff) * dt
        # Guard against runaway integrator
        self.integrator = max(-2.0, min(2.0, self.integrator))
        i_term = self.integrator

        # 7. Schmitt-Trigger Hysteresis Routing Decision
        # Prevents chattering on edge/cloud boundaries
        tier = self._evaluate_hysteresis(u_clamped)

        record = PIDTelemetryRecord(
            timestamp=now,
            setpoint=setpoint,
            measurement=measurement,
            error=error,
            p_term=p_term,
            i_term=i_term,
            d_term=d_term,
            control_output_raw=u_raw,
            control_output_clamped=u_clamped,
            smith_correction=smith_correction,
            hysteresis_state=tier.value,
            target_tier=tier,
        )
        self.history.append(record)
        return record

    def _evaluate_hysteresis(self, u: float) -> RouteTarget:
        """
        Applies dual-threshold Schmitt Trigger with deadband delta to route targets.
        """
        curr = self.current_tier

        if curr == RouteTarget.LOCAL_EDGE_SPSC:
            # Only escalate to REGIONAL if u exceeds (th_low_mid + delta)
            if u > (self.th_low_mid + self.delta):
                if u > (self.th_mid_high + self.delta):
                    self.current_tier = RouteTarget.SOVEREIGN_CLOUD_TEACHER
                else:
                    self.current_tier = RouteTarget.REGIONAL_DISTILLED_SLM

        elif curr == RouteTarget.REGIONAL_DISTILLED_SLM:
            # Escalate to CLOUD if u exceeds (th_mid_high + delta)
            if u > (self.th_mid_high + self.delta):
                self.current_tier = RouteTarget.SOVEREIGN_CLOUD_TEACHER
            # De-escalate to EDGE if u drops below (th_low_mid - delta)
            elif u < (self.th_low_mid - self.delta):
                self.current_tier = RouteTarget.LOCAL_EDGE_SPSC

        elif curr == RouteTarget.SOVEREIGN_CLOUD_TEACHER:
            # De-escalate to REGIONAL only if u drops below (th_mid_high - delta)
            if u < (self.th_mid_high - self.delta):
                if u < (self.th_low_mid - self.delta):
                    self.current_tier = RouteTarget.LOCAL_EDGE_SPSC
                else:
                    self.current_tier = RouteTarget.REGIONAL_DISTILLED_SLM

        return self.current_tier

    def get_status_summary(self) -> Dict[str, Any]:
        """Returns JSON-serializable telemetry state."""
        if not self.history:
            return {
                "active_tier": self.current_tier.value,
                "history_length": 0,
                "kp": self.kp,
                "ki": self.ki,
                "kd": self.kd,
            }
        latest = self.history[-1]
        return {
            "active_tier": self.current_tier.value,
            "last_timestamp": latest.timestamp,
            "setpoint": round(latest.setpoint, 4),
            "measurement": round(latest.measurement, 4),
            "error": round(latest.error, 4),
            "control_u": round(latest.control_output_clamped, 4),
            "smith_correction": round(latest.smith_correction, 4),
            "p_term": round(latest.p_term, 4),
            "i_term": round(latest.i_term, 4),
            "d_term": round(latest.d_term, 4),
            "history_length": len(self.history),
        }
