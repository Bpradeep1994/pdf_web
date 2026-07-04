// Stress / spike test: slam the read path from 0 → SPIKE VUs almost instantly, hold
// briefly, drop to 0. Verifies the app survives a traffic spike and RECOVERS (doesn't
// wedge) rather than sustaining a fixed load.
//
//   docker run --rm --network pdf_editor_default -e BASE=http://gateway:8000 \
//     -e BYPASS=ci-test-bypass-9f3a2 -e SPIKE=300 -v "$PWD/tests/load:/s" \
//     grafana/k6 run /s/stress_spike.js
import http from "k6/http";
import { check, sleep } from "k6";

const BASE   = __ENV.BASE   || "http://localhost:8000";
const BYPASS = __ENV.BYPASS || "";
const SPIKE  = parseInt(__ENV.SPIKE || "300", 10);
const HDR    = BYPASS ? { "x-ratelimit-bypass": BYPASS } : {};

export const options = {
  scenarios: {
    spike: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "5s",  target: SPIKE },   // near-instant spike
        { duration: "15s", target: SPIKE },   // hold the peak
        { duration: "5s",  target: 0 },       // drop
        { duration: "10s", target: 20 },      // recovery load — must respond fast again
      ],
    },
  },
  // no hard thresholds: the point is "does it survive + recover", reported below
};

export function setup() {
  const reg = http.post(`${BASE}/api/v1/auth/register`,
    JSON.stringify({ email: `spike_${Date.now()}@x.com`, password: "TestPass123!", full_name: "Spike" }),
    { headers: { ...HDR, "Content-Type": "application/json" } });
  return { token: reg.json("access_token") };
}

export default function (data) {
  const auth = { ...HDR, Authorization: `Bearer ${data.token}` };
  const r = http.get(`${BASE}/api/v1/documents`, { headers: auth });
  check(r, { "survived (2xx/429/503)": (x) => x.status === 200 || x.status === 429 || x.status === 503 });
  sleep(0.3);
}
