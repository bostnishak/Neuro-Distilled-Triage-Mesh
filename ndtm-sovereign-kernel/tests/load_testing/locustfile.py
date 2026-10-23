"""
NDTM-9000 Sovereign Kernel — Disaster Spike Load Testing Suite (Locust)
Simulates high-velocity crisis event reporting, SRE telemetry scraping,
and Anytime dispatch under strict latency SLOs.
"""

import time
import random
from locust import HttpUser, task, between, events


class DisasterTriageUser(HttpUser):
    wait_time = between(0.01, 0.05)  # High frequency disaster surge
    
    def on_start(self):
        # Set mock auth header for SRE & CRDT authenticated routes
        self.headers = {
            "Authorization": "Bearer sovereign_load_test_token",
            "Content-Type": "application/json",
        }

    @task(5)
    def check_liveness_and_readiness(self):
        """Kubelet & Load Balancer probe barrage."""
        self.client.get("/livez", name="[Probe] GET /livez")

    @task(3)
    def query_sre_telemetry(self):
        """Continuous SRE metrics: PgBouncer routing, partition bounds, Hawkes mesh."""
        self.client.get("/api/v3/sre/db-routing", headers=self.headers, name="[SRE] GET /db-routing")
        self.client.get("/api/v3/sre/partitions", headers=self.headers, name="[SRE] GET /partitions")
        self.client.get("/api/v3/sre/hawkes-mesh", headers=self.headers, name="[SRE] GET /hawkes-mesh")

    @task(2)
    def anytime_dispatch_surge(self):
        """Simulates rapid dispatch requests for 10 incidents across 6 teams."""
        payload = {
            "incidents": [
                {
                    "id": f"inc_{random.randint(1000, 9999)}",
                    "category": random.choice(["FIRE", "HAZMAT", "STRUCTURAL"]),
                    "urgency": random.choice(["HIGH", "CRITICAL"]),
                    "lat": 41.01 + random.random() * 0.05,
                    "lon": 28.98 + random.random() * 0.05,
                    "criticality": 1.0 + random.random(),
                }
                for _ in range(10)
            ],
            "teams": [
                {
                    "id": f"team_{i}",
                    "specialization": random.choice(["FIRE", "HAZMAT", "STRUCTURAL"]),
                    "burnout_index": random.random() * 0.5,
                    "lat": 41.00 + random.random() * 0.05,
                    "lon": 28.97 + random.random() * 0.05,
                    "is_available": True,
                }
                for i in range(6)
            ],
            "deadline_ms": 30,
        }
        self.client.post("/api/v3/sre/dispatch-anytime", json=payload, headers=self.headers, name="[Dispatch] POST /dispatch-anytime")

    @task(2)
    def crdt_event_mutation(self):
        """Simulates active-active WAN state mutations across regions."""
        payload = {
            "region_id": random.choice(["us-west-1", "eu-central-1", "ap-southeast-1"]),
            "event_action": random.choice(["OPEN_INCIDENT", "ASSIGN_TEAM"]),
            "entity_id": f"inc_locust_{random.randint(10000, 99999)}",
        }
        self.client.post("/api/v3/crdt/local-event", json=payload, headers=self.headers, name="[CRDT] POST /local-event")
