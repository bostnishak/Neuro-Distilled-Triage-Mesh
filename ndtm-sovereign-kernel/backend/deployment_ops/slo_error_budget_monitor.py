"""
Neuro-Distilled Triage Mesh (NDTM) — Sovereign Distributed & Failure-Proof Kernel
RFC-NDTM-OMEGA: Production Hardening Engine v3.0

Phase 33: SRE Multi-Window Error Budget Monitor
Google SRE Multi-Burn-Rate Alerting Engine (1h, 6h, 24h, 72h Windows) for 99.9% Availability and Latency SLOs.
"""

from __future__ import annotations

import collections
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Deque, Dict, List, Optional, Tuple


class SLOAlertSeverity(str, Enum):
    HEALTHY = "HEALTHY"
    SEV3_NORMAL_AUDIT = "SEV3_NORMAL_AUDIT"
    SEV2_HIGH_TICKET = "SEV2_HIGH_TICKET"
    SEV1_CRITICAL_PAGE = "SEV1_CRITICAL_PAGE"


@dataclass
class SLOWindowStats:
    window_name: str
    window_seconds: float
    burn_rate_threshold: float
    observed_burn_rate: float
    total_events: int
    bad_events: int
    error_rate: float
    is_breached: bool


@dataclass
class SLOAuditReport:
    slo_target_availability: float  # e.g. 0.999 (99.9%)
    total_budget_consumed_pct: float
    remaining_budget_pct: float
    windows: List[SLOWindowStats]
    highest_severity: SLOAlertSeverity
    recommended_action: str


class SLOErrorBudgetMonitor:
    """
    Google SRE Multi-Window Multi-Burn-Rate Engine.
    
    Target: 99.9% Availability (Error Budget = 0.001 = 0.1% failures allowed).
    Windows & Burn Rates:
    - 1 Hour Window:  14.4x burn rate (consumes 2% of 30d budget in 1 hour)  -> SEV1 CRITICAL PAGE
    - 6 Hour Window:   6.0x burn rate (consumes 5% of 30d budget in 6 hours) -> SEV1 CRITICAL PAGE
    - 24 Hour Window:  3.0x burn rate (consumes 10% of 30d budget in 24 hours)-> SEV2 HIGH TICKET
    - 72 Hour Window:  1.0x burn rate (consumes 10% of 30d budget in 3 days) -> SEV3 NORMAL AUDIT
    """

    def __init__(self, target_slo: float = 0.999, history_retention_hours: float = 72.0):
        self.target_slo = target_slo
        self.max_allowed_error_rate = 1.0 - target_slo  # 0.001
        self.max_retention_sec = history_retention_hours * 3600.0

        # Ring buffer of (timestamp, is_bad_event)
        self.events: Deque[Tuple[float, bool]] = collections.deque()

        # Configured Evaluation Windows: (name, duration_seconds, burn_threshold, sev_if_breached)
        self.window_configs = [
            ("1h_window", 3600.0, 14.4, SLOAlertSeverity.SEV1_CRITICAL_PAGE),
            ("6h_window", 21600.0, 6.0, SLOAlertSeverity.SEV1_CRITICAL_PAGE),
            ("24h_window", 86400.0, 3.0, SLOAlertSeverity.SEV2_HIGH_TICKET),
            ("72h_window", 259200.0, 1.0, SLOAlertSeverity.SEV3_NORMAL_AUDIT),
        ]

    def record_request(self, is_error_or_slow: bool, timestamp: Optional[float] = None) -> None:
        """Records a single service transaction."""
        now = timestamp if timestamp is not None else time.time()
        self.events.append((now, is_error_or_slow))

        # Evaporate events older than max_retention_sec
        cutoff = now - self.max_retention_sec
        while self.events and self.events[0][0] < cutoff:
            self.events.popleft()

    def evaluate_error_budget(self, current_ts: Optional[float] = None) -> SLOAuditReport:
        """Evaluates all multi-burn-rate windows against live event buffer."""
        now = current_ts if current_ts is not None else time.time()

        window_results: List[SLOWindowStats] = []
        highest_sev = SLOAlertSeverity.HEALTHY

        # Total 30-day budget consumption estimation based on 72h window
        total_30d_consumed_pct = 0.0

        for w_name, w_sec, th_burn, sev in self.window_configs:
            cutoff = now - w_sec
            # Filter events in window
            w_events = [e for e in self.events if e[0] >= cutoff]
            total_count = len(w_events)
            bad_count = sum(1 for e in w_events if e[1])

            if total_count == 0:
                err_rate = 0.0
                burn_rate = 0.0
            else:
                err_rate = bad_count / float(total_count)
                # Burn Rate = Observed Error Rate / Allowed Error Rate
                burn_rate = err_rate / self.max_allowed_error_rate

            breached = burn_rate >= th_burn and total_count >= 10

            if breached:
                if sev == SLOAlertSeverity.SEV1_CRITICAL_PAGE:
                    highest_sev = SLOAlertSeverity.SEV1_CRITICAL_PAGE
                elif sev == SLOAlertSeverity.SEV2_HIGH_TICKET and highest_sev != SLOAlertSeverity.SEV1_CRITICAL_PAGE:
                    highest_sev = SLOAlertSeverity.SEV2_HIGH_TICKET
                elif sev == SLOAlertSeverity.SEV3_NORMAL_AUDIT and highest_sev == SLOAlertSeverity.HEALTHY:
                    highest_sev = SLOAlertSeverity.SEV3_NORMAL_AUDIT

            if w_name == "72h_window":
                # 72 hours is 10% of a 30-day month (720 hours)
                # Consumed budget = (burn_rate * 0.10) * 100%
                total_30d_consumed_pct = min(100.0, burn_rate * 10.0)

            window_results.append(
                SLOWindowStats(
                    window_name=w_name,
                    window_seconds=w_sec,
                    burn_rate_threshold=th_burn,
                    observed_burn_rate=round(burn_rate, 3),
                    total_events=total_count,
                    bad_events=bad_count,
                    error_rate=round(err_rate, 6),
                    is_breached=breached,
                )
            )

        remaining_budget = max(0.0, round(100.0 - total_30d_consumed_pct, 2))

        if highest_sev == SLOAlertSeverity.SEV1_CRITICAL_PAGE:
            action = "EMERGENCY: Immediate paging of on-call SRE. Halt all deployments and freeze feature releases."
        elif highest_sev == SLOAlertSeverity.SEV2_HIGH_TICKET:
            action = "HIGH PRIORITY: File Jira urgent remediation ticket. Inspect canary logs and recent migrations."
        elif highest_sev == SLOAlertSeverity.SEV3_NORMAL_AUDIT:
            action = "AUDIT: Elevated baseline burn rate. Review service telemetry in next weekly SRE sync."
        else:
            action = "OPTIMAL: All SLO error budget burn rates within carrier-grade tolerances."

        return SLOAuditReport(
            slo_target_availability=self.target_slo,
            total_budget_consumed_pct=round(total_30d_consumed_pct, 2),
            remaining_budget_pct=remaining_budget,
            windows=window_results,
            highest_severity=highest_sev,
            recommended_action=action,
        )
