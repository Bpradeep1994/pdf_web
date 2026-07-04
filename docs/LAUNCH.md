# 🚀 Launch Runbook

The single top-to-bottom checklist to take PDF Editor live for global internet users.
Work through it in order. Detailed steps live in the linked docs.

- Deployment details → [GO_LIVE.md](GO_LIVE.md)
- Payments / getting paid → [PAYMENTS.md](PAYMENTS.md)
- Global edge / TLS → [CLOUDFLARE.md](CLOUDFLARE.md)
- Performance → [PERF.md](PERF.md)

---

## Phase 1 — Accounts & prep (start ~1 week out)

The slow, sequential stuff. Start the ⏳ items first — they gate everything.

- [ ] ⏳ **Razorpay account + KYC** — PAN, business details, **bank account linked**. Takes days to clear. ([PAYMENTS.md](PAYMENTS.md))
- [ ] **Domain** purchased.
- [ ] **Email provider** (Resend / SES) → SMTP credentials.
- [ ] **VPS** (16 GB RAM recommended) provisioned; Docker + compose installed.
- [ ] **Managed Postgres** (Neon/Supabase) with automated backups, OR the backup script scheduled off-box.
- [ ] **Cloudflare** account; domain added; nameservers set at registrar.
- [ ] **Sentry** project + **UptimeRobot** monitor created.
- [ ] **Privacy Policy + Terms of Service** published (mandatory for EU/global users).

## Phase 2 — Configure (the day before)

- [ ] `cp .env.production.example .env.production`
- [ ] **Regenerate every secret** (`python -c "import secrets;print(secrets.token_urlsafe(48))"`).
- [ ] `RATE_LIMIT_BYPASS_TOKEN` is **empty**; `ENVIRONMENT=production`.
- [ ] Fill in: domains, DB URL, SMTP, **Razorpay live keys + webhook secret + prices**, `ACME_EMAIL`.
- [ ] Register the Razorpay webhook → `https://api.<domain>/api/v1/billing/webhook/razorpay`.
- [ ] Confirm DNS `A` records (`app`, `api`) point at the VPS, **Proxied (orange)**. ([CLOUDFLARE.md](CLOUDFLARE.md))

## Phase 3 — Deploy (launch day)

- [ ] On the VPS: `./deploy/deploy.sh`  → builds, migrates, health-checks, smoke-tests.
- [ ] Cloudflare: **SSL/TLS → Full (strict)**, enable **WebSockets**, **Bot Fight Mode**.
- [ ] VPS firewall: `ufw allow OpenSSH; ufw allow 80,443/tcp; ufw enable`.
- [ ] Point Sentry DSN + UptimeRobot at `https://api.<domain>/health`.

## Phase 4 — Go / No-Go gate (verify before announcing)

Do NOT open to the public until every box is checked:

- [ ] `https://app.<domain>` loads over HTTPS; no cert warnings.
- [ ] **Register → verify email** works (real email arrives).
- [ ] **Password reset** works.
- [ ] **Upload → edit → save → download** a PDF works.
- [ ] **Upgrade to Pro** with a **real card** → money shows in Razorpay → user becomes Pro.
      *(Test with `rzp_test_` keys first, then a small real transaction.)*
- [ ] **Refund** that test payment works.
- [ ] `python tests/smoke_staging.py` against the live URL → **SMOKE PASSED**.
- [ ] Sentry receives a test error; UptimeRobot shows "up".
- [ ] Load test on the real box → read p95 < 800 ms, <1% errors ([PERF.md](PERF.md)).

### Release criteria (already verified in test; re-confirm live)
| Criterion | Status |
|---|---|
| Critical user journeys pass | ✅ (32 browser tests) |
| No Critical/High bugs | ✅ |
| Core features ≥99% pass | ✅ (100%) |
| Avg API < 500 ms | ✅ (67 ms) |
| Security checks pass | ✅ |
| Accessibility (WCAG AA) | ✅ |
| Cross-browser | ⚠️ Chromium-only — state supported browsers, or test Safari/Firefox |
| Smoke after deploy | ⬜ run it live (above) |

## Phase 5 — Soft launch → public

- [ ] **Private beta**: invite 5–10 trusted users. Watch Sentry/Grafana for 3–7 days.
- [ ] Fix anything that surfaces (real users find what tests don't).
- [ ] **Public launch** — announce. Keep dashboards open the first 48 h.
- [ ] Watch: error rate, response times, signups, **first real payments settling to your bank**.

## Phase 6 — Operate

- [ ] **Backups**: confirm they run AND do a **restore drill** on a throwaway box.
- [ ] **Scale when needed**: bigger VPS → Postgres read-replica → the Helm chart (HPA + probes) for multi-node. Not before traffic demands it.
- [ ] **Abuse handling**: a way for users to report content; a takedown process.

---

## 🔥 Emergency procedures

**Rollback a bad deploy**
```bash
git checkout <previous-tag> && ./deploy/deploy.sh
```

**Something is down** — triage order:
1. `docker compose ps` — any service unhealthy/restarting?
2. `docker compose logs --tail=100 <service>` — errors?
3. Infra up? (postgres/redis/rabbitmq/minio healthy?)
4. Cloudflare status page + your VPS provider status.

**Known resilience behavior** (built in):
- Redis down → rate limiting fails open, API keeps serving.
- S3/MinIO down → uploads return a clean 503, reads keep working.
- DB restart → connections auto-reconnect (pool_pre_ping).
- Upstream service down → gateway returns 503, not a crash.

---

## ⚠️ Honest pre-launch reminders

- **Payments are real now** — test with `rzp_test_` keys before switching to `rzp_live_`.
- **Razorpay pays out only after KYC clears** — start it early.
- **You are NOT SOC 2 / GDPR certified** — don't claim it; the marketing copy is already honest.
- **Cross-browser** is Chromium-verified only — decide your supported-browser policy.
- **Get a professional security review** before scaling — the built-in tests aren't a pentest.
- **Legal**: you're responsible for tax on revenue and for a lawful privacy policy.
