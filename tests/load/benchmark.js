// k6 performance benchmark — gates PRs on latency/error regressions.
// Exercises a real authenticated read path through the gateway (not just /health).
//   docker run --rm --network pdf_editor_default -e BASE=http://gateway:8000 \
//     -e BYPASS=ci-test-bypass-9f3a2 -v "$PWD/tests/load:/s" grafana/k6 run /s/benchmark.js
import http from "k6/http";
import { check, sleep } from "k6";

const BASE   = __ENV.BASE   || "http://localhost:8000";
const BYPASS = __ENV.BYPASS || "";
const H = { "x-ratelimit-bypass": BYPASS, "Content-Type": "application/json" };

export const options = {
  scenarios: {
    // modest, runner-appropriate load — this GATES read-path regressions (e.g. an
    // accidental N+1), it is NOT a capacity test (real numbers need a dedicated rig).
    load: { executor: "ramping-vus", startVUs: 0,
      stages: [{ duration: "10s", target: 20 }, { duration: "25s", target: 20 }, { duration: "5s", target: 0 }] },
  },
  thresholds: {
    http_req_failed:                ["rate<0.01"],   // <1% errors — gated
    "http_req_duration{kind:read}": ["p(95)<800"],   // authed read hot-path p95 < 800ms — gated
    // NOTE: auth (register/login) is bcrypt-bound and CPU-heavy; its latency swings
    // with runner capacity, so it is measured & printed but deliberately NOT gated
    // (gating bcrypt on shared CI runners is flaky). See docs/PERF.md.
  },
};

export function setup() {
  const email = `bench_${Date.now()}@x.com`;
  const r = http.post(`${BASE}/api/v1/auth/register`,
    JSON.stringify({ email, password: "TestPass123!", full_name: "Bench" }),
    { headers: H, tags: { kind: "auth" } });   // measured, not gated
  return { token: r.json("access_token") };
}

export default function (data) {
  const authed = { ...H, Authorization: `Bearer ${data.token}` };
  const reads = [
    http.get(`${BASE}/api/v1/documents`,            { headers: authed, tags: { kind: "read" } }),
    http.get(`${BASE}/api/v1/auth/me`,              { headers: authed, tags: { kind: "read" } }),
    http.get(`${BASE}/api/v1/billing/subscription`, { headers: authed, tags: { kind: "read" } }),
  ];
  reads.forEach((r) => check(r, { "status 200": (res) => res.status === 200 }));
  sleep(1);
}
