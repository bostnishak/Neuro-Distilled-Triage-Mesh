"""Locust Load Testing Suite for Neuro-Distilled Triage Mesh (NDTM).
Simulates high-throughput concurrent incident reporting, model routing, and symbolic solving.
"""
from __future__ import annotations

import random
import time
from uuid import uuid4

from locust import HttpUser, between, task


SAMPLE_INCIDENTS = [
    {
        "description": "Kadıköy rıhtım caddesinde elektrik kablosu koptu, yerde kıvılcım saçıyor.",
        "category": "ELECTRICAL_FIRE",
        "urgency_score": 5,
        "latitude": 40.9902,
        "longitude": 29.0234,
    },
    {
        "description": "Beşiktaş meydanında ana su borusu patladı ve tünel girişine su doluyor.",
        "category": "WATER_MAIN_BURST",
        "urgency_score": 4,
        "latitude": 41.0422,
        "longitude": 29.0067,
    },
    {
        "description": "Şişli Mecidiyeköy viyadüğü altında doğalgaz kokusu alınıyor, şiddetli sızıntı var.",
        "category": "GAS_LEAK",
        "urgency_score": 5,
        "latitude": 41.0667,
        "longitude": 28.9950,
    },
    {
        "description": "Yol ortasında büyük bir çukur meydana geldi, araçlar manevra yapamıyor.",
        "category": "ROAD_COLLAPSE",
        "urgency_score": 3,
        "latitude": 41.0100,
        "longitude": 28.9700,
    },
]


class NDTMUser(HttpUser):
    wait_time = between(0.1, 0.5)

    def on_start(self):
        """Simulate authentication login or operator session token."""
        self.auth_token = "bearer-load-test-token"
        self.headers = {
            "Authorization": f"Bearer {self.auth_token}",
            "Content-Type": "application/json",
        }

    @task(5)
    def test_semantic_router_inference(self):
        """High-frequency query to the DistillMesh router to evaluate INT8 student vs Teacher LLM."""
        incident = random.choice(SAMPLE_INCIDENTS)
        payload = {"text": incident["description"]}
        self.client.post(
            "/api/v1/router/infer",
            json=payload,
            headers=self.headers,
            name="/api/v1/router/infer",
        )

    @task(3)
    def test_triage_incident_submission(self):
        """Ingests full incident report with spatial coordinates and idempotency key."""
        incident = random.choice(SAMPLE_INCIDENTS)
        # Add random jitter to coordinates within 200m to exercise spatial deduplication
        lat_jitter = random.uniform(-0.001, 0.001)
        lon_jitter = random.uniform(-0.001, 0.001)

        payload = {
            "description": incident["description"],
            "category": incident["category"],
            "latitude": incident["latitude"] + lat_jitter,
            "longitude": incident["longitude"] + lon_jitter,
            "urgency_score": incident["urgency_score"],
            "image_base64": None,
        }

        idempotency_key = f"load-{uuid4()}"
        headers = {**self.headers, "Idempotency-Key": idempotency_key}

        self.client.post(
            "/api/v1/triage/incidents",
            json=payload,
            headers=headers,
            name="/api/v1/triage/incidents",
        )

    @task(1)
    def test_symbolic_scheduler_solve(self):
        """Periodic trigger to the Z3 SMT solver."""
        payload = {
            "incidents": [
                {
                    "incident_id": str(uuid4()),
                    "category": "ELECTRICAL_FIRE",
                    "required_skill": "HIGH_VOLTAGE_SAFETY",
                    "latitude": 41.0082,
                    "longitude": 28.9784,
                    "urgency_score": 5,
                    "estimated_work_minutes": 45,
                }
            ],
            "teams": [
                {
                    "id": str(uuid4()),
                    "team_code": f"LOAD-TEAM-{random.randint(1, 99)}",
                    "skills": ["HIGH_VOLTAGE_SAFETY", "ELECTRICAL"],
                    "shift_remaining_minutes": 180,
                    "max_concurrent_tasks": 2,
                    "latitude": 41.005,
                    "longitude": 28.975,
                    "is_available": True,
                }
            ],
        }
        self.client.post(
            "/api/v1/scheduler/solve",
            json=payload,
            headers=self.headers,
            name="/api/v1/scheduler/solve",
        )

    @task(2)
    def test_metrics_snapshot(self):
        """Health and metrics polling task."""
        self.client.get(
            "/api/v1/system/metrics-snapshot",
            headers=self.headers,
            name="/api/v1/system/metrics-snapshot",
        )
