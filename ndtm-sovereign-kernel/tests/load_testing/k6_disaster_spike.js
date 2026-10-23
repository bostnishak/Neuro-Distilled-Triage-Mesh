import http from 'k6/http';
import { check, sleep } from 'k6';

// NDTM-9000 Sovereign Kernel Disaster Peak Load Test Scenario
// Simulates an earthquake or large-scale urban disaster incident surge (10k+ rps)
export const options = {
  stages: [
    { duration: '15s', target: 50 },    // Warmup
    { duration: '30s', target: 500 },   // Initial shockwave
    { duration: '1m',  target: 2000 },  // Peak disaster event reporting surge
    { duration: '30s', target: 500 },   // Gradual stabilization
    { duration: '15s', target: 0 },     // Teardown
  ],
  thresholds: {
    http_req_duration: ['p(95)<30', 'p(99)<60'], // 95% of requests under 30ms, 99% under 60ms
    http_req_failed: ['rate<0.01'],               // Error rate < 1%
  },
};

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';

export default function () {
  const payload = JSON.stringify({
    title: 'Yangın ve Gaz Kokusu Bildirimi',
    description: 'Kadıköy Rıhtım caddesinde elektrik trafosu patladı, yangın ve yoğun duman var. Vatandaş TC: 10000000146, tel: 05321234567 acil yardım istiyor.',
    urgency: 'HIGH',
    category: 'FIRE',
    modality: 'TEXT',
    latitude: 40.9912 + (Math.random() - 0.5) * 0.05,
    longitude: 29.0234 + (Math.random() - 0.5) * 0.05,
  });

  const params = {
    headers: {
      'Content-Type': 'application/json',
      'Idempotency-Key': `k6_${__VU}_${__ITER}_${Date.now()}`,
    },
  };

  // 1. Ingest Incident
  const res = http.post(`${BASE_URL}/api/v1/incidents`, payload, params);
  check(res, {
    'incident status is 200 or 201': (r) => r.status === 200 || r.status === 201,
    'has triage state': (r) => r.json('triage_state') !== undefined,
  });

  // 2. Health & Readiness Probe Check
  if (__ITER % 25 === 0) {
    const readyRes = http.get(`${BASE_URL}/readyz`);
    check(readyRes, {
      'readyz is 200': (r) => r.status === 200,
    });
  }

  sleep(0.05); // Rapid concurrent dispatch
}
