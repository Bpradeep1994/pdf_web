# Performance benchmark (CI gate)

`tests/load/benchmark.js` runs in the **Performance** stage of the PR pipeline
(`.github/workflows/ci.yml`) via the `grafana/k6` container against an ephemeral
compose stack.

## What it gates

| Metric | Threshold | Rationale |
|---|---|---|
| `http_req_failed` | `< 1%` | any error-rate regression fails the build |
| authed read p95 (`kind:read`) | `< 800ms` | the hot path (`/documents`, `/auth/me`, `/billing/subscription`) — catches N+1s and slow-query regressions |

## What it deliberately does NOT gate

Auth latency (`register` / `login`) is **measured and printed but not gated**. Those
endpoints are bcrypt-bound (intentionally CPU-expensive); their latency swings widely
with the runner's available CPU, so a tight threshold flakes on shared CI runners.
A gross auth regression still shows up in the printed p95.

## This is a regression gate, not a capacity test

The load is modest (≈20 VUs) so it runs quickly and stably on a CI runner. It answers
"did this PR make the hot path slower / more error-prone?" — **not** "how many
concurrent users can we serve?". Real capacity numbers (100 → 10k users) require a
dedicated load rig where the generator and the app under test run on separate hardware;
running both on one machine measures the machine, not the service.

Run locally against the compose stack:

```bash
docker run --rm --network pdf_editor_default \
  -e BASE=http://gateway:8000 -e BYPASS=$RATE_LIMIT_BYPASS_TOKEN \
  -v "$PWD/tests/load:/s" grafana/k6 run /s/benchmark.js
```
