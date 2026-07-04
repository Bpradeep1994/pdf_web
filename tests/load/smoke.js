// k6 load test — gateway baseline. Run:
//   docker run --rm --network pdf_editor_default -e BASE=http://gateway:8000 \
//     -v "$PWD/tests/load:/s" grafana/k6 run /s/smoke.js
import http from "k6/http";
import { check } from "k6";

export const options = {
  scenarios: {
    ramp: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "10s", target: 50 },   // ramp to 50 virtual users
        { duration: "20s", target: 50 },   // hold
        { duration: "5s",  target: 0 },    // ramp down
      ],
    },
  },
  thresholds: {
    http_req_duration: ["p(95)<500"],   // 95% of requests under 500ms
    http_req_failed:   ["rate<0.01"],   // <1% errors
  },
};

const BASE = __ENV.BASE || "http://localhost:8000";

export default function () {
  // /health is not rate-limited (the per-IP limiter only guards /api/v1/*),
  // so this measures raw gateway throughput/latency.
  const r = http.get(`${BASE}/health`);
  check(r, { "status 200": (res) => res.status === 200 });
}
