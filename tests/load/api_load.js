// Realistic API load test — exercises auth + core read/write endpoints through the
// gateway, not just /health. Tiered via the TIER env var.
//
//   docker run --rm --network pdf_editor_default \
//     -e BASE=http://gateway:8000 -e BYPASS=ci-test-bypass-9f3a2 -e TIER=100 \
//     -v "$PWD/tests/load:/s" grafana/k6 run /s/api_load.js
//
// TIER = target concurrent VUs (100 | 500 | 1000 | …). The load generator and the
// app share this machine, so treat high tiers as directional, not authoritative.
import http from "k6/http";
import { check, sleep } from "k6";
import { Trend } from "k6/metrics";

const BASE   = __ENV.BASE   || "http://localhost:8000";
const BYPASS = __ENV.BYPASS || "";
const TIER   = parseInt(__ENV.TIER || "100", 10);

const listLatency = new Trend("list_latency", true);

export const options = {
  scenarios: {
    ramp: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "15s", target: TIER },   // ramp up
        { duration: "40s", target: TIER },   // hold at target
        { duration: "10s", target: 0 },      // ramp down
      ],
      gracefulRampDown: "10s",
    },
  },
  thresholds: {
    http_req_failed:   ["rate<0.02"],   // <2% errors
    http_req_duration: ["p(95)<1500"],  // 95% under 1.5s under load
  },
};

const HDR = BYPASS ? { "x-ratelimit-bypass": BYPASS } : {};

// Real users register ONCE and then browse. Registering every iteration would make
// this a bcrypt benchmark, not an API load test — so pre-create a token pool in
// setup() and have VUs reuse it in the read-heavy hot loop.
const POOL = Math.min(40, Math.max(10, Math.floor(TIER / 10)));

export function setup() {
  const tokens = [];
  for (let i = 0; i < POOL; i++) {
    const reg = http.post(`${BASE}/api/v1/auth/register`,
      JSON.stringify({ email: `load_pool_${i}_${Date.now()}@x.com`, password: "TestPass123!", full_name: "Load" }),
      { headers: { ...HDR, "Content-Type": "application/json" } });
    if (reg.status === 201) tokens.push(reg.json("access_token"));
  }
  return { tokens };
}

export default function (data) {
  const token = data.tokens[__VU % data.tokens.length];
  const auth = { ...HDR, Authorization: `Bearer ${token}` };

  // dashboard hot path: list documents
  const t0 = Date.now();
  const list = http.get(`${BASE}/api/v1/documents`, { headers: auth });
  listLatency.add(Date.now() - t0);
  check(list, { "list 200": (r) => r.status === 200 });

  // profile + subscription reads (also hot on page load)
  check(http.get(`${BASE}/api/v1/auth/me`, { headers: auth }), { "me 200": (r) => r.status === 200 });
  check(http.get(`${BASE}/api/v1/billing/subscription`, { headers: auth }), { "sub 200": (r) => r.status === 200 });

  sleep(Math.random() * 1.5 + 0.5);   // think time 0.5–2s
}
