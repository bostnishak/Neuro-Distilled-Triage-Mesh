"""
Neuro-Distilled Triage Mesh (NDTM) — Sovereign Distributed & Failure-Proof Kernel
RFC-NDTM-OMEGA: Production Hardening Engine v3.0

Phase 33: Read/Write Split Connection Pool Router
Multiplexes High-Throughput DB Queries Across PgBouncer Transaction Pools (ndtm_pool_rw & ndtm_pool_ro).
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional, Tuple


class DBPoolTarget(str, Enum):
    PRIMARY_WRITE = "ndtm_pool_rw"
    REPLICA_READ = "ndtm_pool_ro"


@dataclass
class RouteInspectionResult:
    target_pool: DBPoolTarget
    is_write: bool
    requires_transaction: bool
    matched_clause: str


class RWSplitConnectionRouter:
    """
    Carrier-Grade SQL Query Classifier and Connection Pool Router.
    
    Guarantees that write operations never touch read replicas,
    and heavy analytical/read queries never contend with primary write transactions.
    """

    WRITE_PATTERNS = [
        re.compile(r"^\s*INSERT\b", re.IGNORECASE),
        re.compile(r"^\s*UPDATE\b", re.IGNORECASE),
        re.compile(r"^\s*DELETE\b", re.IGNORECASE),
        re.compile(r"^\s*CREATE\b", re.IGNORECASE),
        re.compile(r"^\s*DROP\b", re.IGNORECASE),
        re.compile(r"^\s*ALTER\b", re.IGNORECASE),
        re.compile(r"^\s*TRUNCATE\b", re.IGNORECASE),
        re.compile(r"\bFOR\s+UPDATE\b", re.IGNORECASE),
        re.compile(r"\bFOR\s+SHARE\b", re.IGNORECASE),
        re.compile(r"^\s*CALL\b", re.IGNORECASE),
        # Catch modifying CTEs: WITH ... INSERT / UPDATE / DELETE ...
        re.compile(r"^\s*WITH\b[\s\S]*?\b(INSERT\s+INTO|UPDATE\b|DELETE\s+FROM)\b", re.IGNORECASE),
        re.compile(r"\b(INSERT\s+INTO|UPDATE\s+[a-zA-Z0-9_\.]+\s+SET|DELETE\s+FROM)\b", re.IGNORECASE),
    ]

    def __init__(
        self,
        rw_pool_dsn: Optional[str] = None,
        ro_pool_dsn: Optional[str] = None,
    ):
        import os
        self.rw_dsn = rw_pool_dsn or os.getenv("DB_PGBOUNCER_RW_DSN", "postgresql://ndtm_mesh@localhost:6432/ndtm_pool_rw")
        self.ro_dsn = ro_pool_dsn or os.getenv("DB_PGBOUNCER_RO_DSN", "postgresql://ndtm_mesh@localhost:6432/ndtm_pool_ro")
        self.lock = threading.RLock()

        # Telemetry metrics
        self.routed_reads_count: int = 0
        self.routed_writes_count: int = 0

    def inspect_query(self, sql_query: str) -> RouteInspectionResult:
        """Classifies SQL statement into PRIMARY_WRITE or REPLICA_READ."""
        normalized = sql_query.strip()

        for pattern in self.WRITE_PATTERNS:
            match = pattern.search(normalized)
            if match:
                return RouteInspectionResult(
                    target_pool=DBPoolTarget.PRIMARY_WRITE,
                    is_write=True,
                    requires_transaction=True,
                    matched_clause=match.group(0),
                )

        return RouteInspectionResult(
            target_pool=DBPoolTarget.REPLICA_READ,
            is_write=False,
            requires_transaction=False,
            matched_clause="SELECT_READONLY",
        )

    def route_query(self, sql_query: str) -> Tuple[str, DBPoolTarget]:
        """
        Returns connection DSN and target pool for a given SQL query.
        """
        res = self.inspect_query(sql_query)
        with self.lock:
            if res.is_write:
                self.routed_writes_count += 1
                return self.rw_dsn, DBPoolTarget.PRIMARY_WRITE
            else:
                self.routed_reads_count += 1
                return self.ro_dsn, DBPoolTarget.REPLICA_READ

    def get_router_telemetry(self) -> Dict[str, Any]:
        with self.lock:
            total = self.routed_reads_count + self.routed_writes_count
            read_pct = (self.routed_reads_count / float(total) * 100.0) if total > 0 else 100.0
            return {
                "total_queries_routed": total,
                "read_queries_count": self.routed_reads_count,
                "write_queries_count": self.routed_writes_count,
                "read_offload_percentage": round(read_pct, 2),
                "rw_pool": DBPoolTarget.PRIMARY_WRITE.value,
                "ro_pool": DBPoolTarget.REPLICA_READ.value,
            }
