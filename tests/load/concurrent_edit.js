// Concurrent-editing load: many VUs hammer edits + undo on ONE shared document,
// exercising the per-document advisory lock and version-write path under contention.
//
//   docker run --rm --network pdf_editor_default -e BASE=http://gateway:8000 \
//     -e BYPASS=ci-test-bypass-9f3a2 -e VUS=50 -v "$PWD/tests/load:/s" \
//     grafana/k6 run /s/concurrent_edit.js
import http from "k6/http";
import { check, sleep } from "k6";

const BASE   = __ENV.BASE   || "http://localhost:8000";
const BYPASS = __ENV.BYPASS || "";
const VUS    = parseInt(__ENV.VUS || "50", 10);
const HDR    = BYPASS ? { "x-ratelimit-bypass": BYPASS } : {};

const PDF =
  "%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n" +
  "2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n" +
  "3 0 obj<</Type/Page/MediaBox[0 0 400 400]/Parent 2 0 R>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF";

export const options = {
  scenarios: {
    edit: { executor: "constant-vus", vus: VUS, duration: "40s" },
  },
  thresholds: {
    // contention may serialize writes → allow generous latency, but errors must stay low
    http_req_failed:   ["rate<0.05"],
    "checks{type:edit}": ["rate>0.9"],
  },
};

// one shared owner + document that every VU edits concurrently
export function setup() {
  const email = `edit_owner_${Date.now()}@x.com`;
  const reg = http.post(`${BASE}/api/v1/auth/register`,
    JSON.stringify({ email, password: "TestPass123!", full_name: "Owner" }),
    { headers: { ...HDR, "Content-Type": "application/json" } });
  const token = reg.json("access_token");
  const auth = { ...HDR, Authorization: `Bearer ${token}` };
  const up = http.post(`${BASE}/api/v1/documents`,
    { file: http.file(PDF, "shared.pdf", "application/pdf") }, { headers: auth });
  return { auth, docId: up.json("id") };
}

export default function (data) {
  const { auth, docId } = data;
  const body = JSON.stringify({ page: 1, x: 50, y: 50 + (__VU % 300), text: `VU${__VU}-${__ITER}`, size: 10 });
  const edit = http.post(`${BASE}/api/v1/documents/${docId}/edit/text`, body,
    { headers: { ...auth, "Content-Type": "application/json" } });
  check(edit, { "edit ok": (r) => r.status === 200 }, { type: "edit" });

  // half the VUs also undo → maximises version-table contention
  if (__VU % 2 === 0) {
    http.post(`${BASE}/api/v1/documents/${docId}/undo`, null, { headers: auth });
  }
  sleep(Math.random() * 0.5);
}
