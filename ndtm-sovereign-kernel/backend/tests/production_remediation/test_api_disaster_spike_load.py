"""
NDTM-9000 Sovereign Kernel — Comprehensive End-to-End API Load & Disaster Spike Test
Simulates concurrent crisis traffic across core endpoints and security middlewares.
"""

import asyncio
import time
import statistics
import pytest
from httpx import AsyncClient, ASGITransport

from presentation.api.main import app
from core.security_ed25519_jwt import create_access_token


import uuid
from presentation.api.dependencies import get_current_user
from infrastructure.database.orm_models import UserOrm

fake_admin = UserOrm(
    id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
    email="admin@ndtm.gov.tr",
    role="ADMIN",
    is_active=True,
)
app.dependency_overrides[get_current_user] = lambda: fake_admin


@pytest.mark.asyncio
async def test_api_disaster_spike_concurrent_barrage():
    """Simulates simultaneous flood of disaster traffic against SRE, Probes, and Dispatch."""
    transport = ASGITransport(app=app)
    auth_headers = {"Authorization": "Bearer dummy_token"}
    
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Scenario 1: Probes under 500 concurrent requests
        t0 = time.perf_counter()
        probe_tasks = [client.get("/livez") for _ in range(500)]
        probe_responses = await asyncio.gather(*probe_tasks)
        probe_dur = time.perf_counter() - t0
        probe_rps = len(probe_responses) / probe_dur
        
        for r in probe_responses:
            assert r.status_code == 200
            assert r.json()["status"] == "ALIVE"
            
        print(f"\n[API Load - /livez] 500 requests in {probe_dur:.3f}s -> {probe_rps:,.1f} RPS (100% 200 OK)")

        # Scenario 2: SRE Endpoints (db-routing, partitions, hawkes-mesh) under concurrent load
        sre_latencies = []
        endpoints = [
            "/api/v3/sre/db-routing",
            "/api/v3/sre/partitions",
            "/api/v3/sre/hawkes-mesh",
        ]
        
        async def fetch_endpoint(url):
            start = time.perf_counter()
            resp = await client.get(url, headers=auth_headers)
            lat = (time.perf_counter() - start) * 1000.0
            return resp.status_code, lat

        t0 = time.perf_counter()
        sre_tasks = [fetch_endpoint(endpoints[i % len(endpoints)]) for i in range(300)]
        sre_results = await asyncio.gather(*sre_tasks)
        sre_dur = time.perf_counter() - t0
        sre_rps = len(sre_results) / sre_dur
        
        for status, lat in sre_results:
            assert status == 200
            sre_latencies.append(lat)
            
        p50 = statistics.median(sre_latencies)
        p95 = statistics.quantiles(sre_latencies, n=20)[18]
        p99 = statistics.quantiles(sre_latencies, n=100)[98]
        print(f"[API Load - SRE Suite] 300 requests in {sre_dur:.3f}s -> {sre_rps:,.1f} RPS | P50: {p50:.2f}ms | P95: {p95:.2f}ms | P99: {p99:.2f}ms")

        # Scenario 3: Anytime Dispatch under 100 concurrent requests
        dispatch_payload = {
            "incidents": [
                {
                    "id": f"inc_{k}",
                    "category": "FIRE" if k % 2 == 0 else "HAZMAT",
                    "urgency": "CRITICAL" if k % 3 == 0 else "HIGH",
                    "lat": 41.01 + k * 0.001,
                    "lon": 28.98 + k * 0.001,
                    "criticality": 1.5,
                }
                for k in range(8)
            ],
            "teams": [
                {
                    "id": f"team_{m}",
                    "specialization": "FIRE" if m % 2 == 0 else "HAZMAT",
                    "burnout_index": 0.1 * m,
                    "lat": 41.00 + m * 0.002,
                    "lon": 28.97 + m * 0.002,
                    "is_available": True,
                }
                for m in range(5)
            ],
            "deadline_ms": 50,
        }
        
        async def post_dispatch():
            start = time.perf_counter()
            resp = await client.post("/api/v3/sre/dispatch-anytime", json=dispatch_payload, headers=auth_headers)
            lat = (time.perf_counter() - start) * 1000.0
            return resp.status_code, lat

        t0 = time.perf_counter()
        dispatch_tasks = [post_dispatch() for _ in range(50)]
        dispatch_results = await asyncio.gather(*dispatch_tasks)
        dispatch_dur = time.perf_counter() - t0
        dispatch_rps = len(dispatch_results) / dispatch_dur
        
        disp_latencies = []
        for status, lat in dispatch_results:
            assert status == 200
            disp_latencies.append(lat)
            
        p50 = statistics.median(disp_latencies)
        p95 = statistics.quantiles(disp_latencies, n=20)[18]
        p99 = statistics.quantiles(disp_latencies, n=100)[98]
        print(f"[API Load - Anytime Dispatch] 50 batches in {dispatch_dur:.3f}s -> {dispatch_rps:,.1f} RPS | P50: {p50:.2f}ms | P95: {p95:.2f}ms | P99: {p99:.2f}ms")

        # Scenario 4: CRDT Event Ingestion under 200 concurrent writes
        crdt_payload = {
            "region_id": "us-west-1",
            "event_action": "OPEN_INCIDENT",
            "entity_id": "inc_disaster_spike_99",
        }
        
        async def post_crdt():
            start = time.perf_counter()
            resp = await client.post("/api/v3/crdt/local-event", json=crdt_payload, headers=auth_headers)
            lat = (time.perf_counter() - start) * 1000.0
            return resp.status_code, lat

        t0 = time.perf_counter()
        crdt_tasks = [post_crdt() for _ in range(200)]
        crdt_results = await asyncio.gather(*crdt_tasks)
        crdt_dur = time.perf_counter() - t0
        crdt_rps = len(crdt_results) / crdt_dur
        
        crdt_lats = []
        for status, lat in crdt_results:
            assert status == 200
            crdt_lats.append(lat)
            
        p50 = statistics.median(crdt_lats)
        p95 = statistics.quantiles(crdt_lats, n=20)[18]
        p99 = statistics.quantiles(crdt_lats, n=100)[98]
        print(f"[API Load - CRDT Ingest] 200 concurrent events in {crdt_dur:.3f}s -> {crdt_rps:,.1f} RPS | P50: {p50:.2f}ms | P95: {p95:.2f}ms | P99: {p99:.2f}ms")
