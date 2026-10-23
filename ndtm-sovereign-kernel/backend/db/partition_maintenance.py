"""
Neuro-Distilled Triage Mesh (NDTM) — Sovereign Distributed & Failure-Proof Kernel
RFC-NDTM-OMEGA: Production Hardening Engine v3.0

Phase 33: Automated Table Partition Maintenance Engine
Pre-creates Monthly Partitions 3 Months in Advance and Detaches Expired Partitions.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class PartitionMetadata:
    table_name: str
    partition_name: str
    start_date: str
    end_date: str
    is_created: bool
    ddl_statement: str


class PartitionMaintenanceManager:
    """
    Carrier-Grade PostgreSQL Partition Provisioner.
    
    Prevents catastrophic write halts caused by missing monthly partition tables.
    Automatically calculates monthly date bounds and generates idempotent DDL.
    """

    PARTITIONED_TABLES = [
        "incidents_partitioned",
        "router_telemetry_partitioned",
    ]

    def __init__(self, months_ahead: int = 3, retention_months: int = 12):
        self.months_ahead = months_ahead
        self.retention_months = retention_months

    @staticmethod
    def _get_month_bounds(year: int, month: int) -> Tuple[str, str]:
        start_dt = datetime.date(year, month, 1)
        if month == 12:
            next_month_dt = datetime.date(year + 1, 1, 1)
        else:
            next_month_dt = datetime.date(year, month + 1, 1)
        return start_dt.isoformat(), next_month_dt.isoformat()

    def generate_provisioning_ddl(self, anchor_date: Optional[datetime.date] = None) -> List[PartitionMetadata]:
        """
        Generates DDL to pre-create partitions for the current month + months_ahead.
        """
        today = anchor_date or datetime.date.today()
        provisions: List[PartitionMetadata] = []

        curr_year = today.year
        curr_month = today.month

        for offset in range(self.months_ahead + 1):
            m = curr_month + offset
            y = curr_year + (m - 1) // 12
            m = ((m - 1) % 12) + 1

            start_str, end_str = self._get_month_bounds(y, m)
            month_suffix = f"{y}_{m:02d}"

            for base_table in self.PARTITIONED_TABLES:
                part_name = f"{base_table}_{month_suffix}"
                ddl = (
                    f"CREATE TABLE IF NOT EXISTS {part_name} "
                    f"PARTITION OF {base_table} "
                    f"FOR VALUES FROM ('{start_str} 00:00:00+00') TO ('{end_str} 00:00:00+00');"
                )
                provisions.append(
                    PartitionMetadata(
                        table_name=base_table,
                        partition_name=part_name,
                        start_date=start_str,
                        end_date=end_str,
                        is_created=True,
                        ddl_statement=ddl,
                    )
                )

        return provisions

    def generate_retention_cleanup_ddl(self, anchor_date: Optional[datetime.date] = None) -> List[str]:
        """
        Generates DDL to detach partitions older than retention_months.
        """
        today = anchor_date or datetime.date.today()
        detach_ddls: List[str] = []

        # Find target expired year/month
        total_months = today.year * 12 + today.month - self.retention_months - 1
        exp_year = total_months // 12
        exp_month = (total_months % 12) + 1

        month_suffix = f"{exp_year}_{exp_month:02d}"

        for base_table in self.PARTITIONED_TABLES:
            part_name = f"{base_table}_{month_suffix}"
            detach_ddl = f"ALTER TABLE IF EXISTS {base_table} DETACH PARTITION {part_name} CONCURRENTLY;"
            detach_ddls.append(detach_ddl)

        return detach_ddls
