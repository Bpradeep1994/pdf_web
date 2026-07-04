# Go-Live Runbook

A concrete path from local dev to a public deployment. Recommended first target: a
**single VPS running the Docker Compose stack behind Caddy (TLS)** — cheap, simple, and
already supported. Graduate to Kubernetes (the Helm chart in `deploy/helm/`) when traffic
justifies it.

Legend: ✅ code-ready in this repo · ⚠️ needs YOUR account/decision · 🔒 security-critical

---

## 0. Pre-flight checklist (do NOT skip any 🔒)

- [ ] 🔒 Copy `.env.production.example` → `.env.production` and **regenerate every secret**
      (`python -c "import secrets;print(secrets.token_urlsafe(48))"`). Never reuse the samples.
- [ ] 🔒 `RATE_LIMIT_BYPASS_TOKEN` is **empty**. (If set, anyone can bypass rate limiting.)
- [ ] 🔒 `ENVIRONMENT=production` (disables dev-only token echoes for email/OTP).
- [ ] ⚠️ Domain purchased; DNS `A`/`AAAA` records point `app.` and `api.` at the server.
- [ ] ⚠️ Transactional email configured (`SMTP_*`) — else verification/reset emails don't send.
- [ ] ⚠️ Stripe live keys + webhook secret + price IDs set — else you can't charge anyone.
- [ ] ⚠️ Managed Postgres **with automated backups** (or `backend/scripts/backup.sh` on a cron to off-box storage).
- [ ] ⚠️ Error tracking (Sentry) + uptime monitor (UptimeRobot) wired up.
- [ ] ⚠️ Privacy Policy + Terms of Service published (required for EU/global users).

---

## 1. Provision the server (VPS path)

A 2–4 vCPU / 8 GB VPS (DigitalOcean, Hetzner, Linode) is enough for a beta.

```bash
# on the server
sudo apt-get update && sudo apt-get install -y docker.io docker-compose-plugin
git clone <your-repo> && cd pdf_editor
cp .env.production.example .env.production   # then edit + regenerate secrets
```

## 2. TLS + reverse proxy (Caddy)

Caddy auto-provisions Let's Encrypt certs. Point `deploy/caddy/Caddyfile` at your domains,
then bring the stack up **with the tls + av profiles**:

```bash
docker compose --env-file .env.production --profile tls --profile av up -d --build
```

- `tls`  → HTTPS via Caddy (needs ports 80/443 open + DNS resolving to this host)
- `av`   → ClamAV real malware scanning (set `CLAMAV_HOST=clamav`)

## 3. Database migrations

```bash
docker run --rm --network pdf_editor_default -v "$PWD/backend:/app" -w /app \
  -e DATABASE_URL="postgresql+asyncpg://$POSTGRES_USER:$POSTGRES_PASSWORD@postgres:5432/$POSTGRES_DB" \
  python:3.12-slim sh -c "pip install -q -r requirements-migrations.txt && alembic upgrade head"
```

## 4. Monitoring

```bash
docker compose --profile monitoring up -d      # Prometheus + Grafana
```
Then add alert rules (`monitoring/alerts.yml`) and a notification channel (Slack/email/PagerDuty).
Add a hosted uptime check against `https://api.yourdomain.com/health`.

## 5. Smoke test the live deployment

```bash
STAGING_URL=https://api.yourdomain.com python tests/smoke_staging.py
```
Must print `SMOKE PASSED` (health → auth → document round-trip → presigned link → billing).

## 6. Load test on the real box (get your true capacity)

```bash
docker run --rm --network pdf_editor_default -e BASE=http://gateway:8000 \
  -v "$PWD/tests/load:/s" grafana/k6 run /s/benchmark.js
```
See `docs/PERF.md`. This is where the real "how many users can we serve" number comes from —
NOT the local dev runs.

---

## 7. Launch sequence

1. **Private beta** — invite a handful of trusted users. Confirms email + payments actually work.
2. Watch Grafana + Sentry for 1–2 weeks; fix what surfaces.
3. **Limited public launch** (one region). Keep watching dashboards.
4. Scale out — add gateway/pdf_service replicas (compose `--scale`, or move to the Helm chart
   which already has HPA + liveness/readiness probes).

## Rollback

Images are tagged per release. To roll back:
```bash
# VPS: redeploy the previous git tag
git checkout <previous-tag> && docker compose --env-file .env.production up -d --build
# K8s: helm rollback pdf-editor
```

## Backups & restore (test this BEFORE you need it)

- Backup:  `backend/scripts/backup.sh`  (dumps Postgres → `BACKUP_BUCKET`)
- Restore: `backend/scripts/restore.sh`
- **Do a full restore drill on a throwaway instance** so you know it works. An untested backup is not a backup.

---

## Known limitations to disclose / decide on before launch

- **Browser support**: automated tests cover Chromium (desktop + mobile viewport) only.
  Safari/WebKit and Firefox are unverified — either test them manually or state the supported browsers.
- **Compliance**: the app is *not* SOC 2 / GDPR *certified*. Marketing copy has been corrected to
  honest claims ("encrypted in transit & at rest", "delete your data anytime"). Get real
  certification before making compliance claims.
- **Telugu/Tamil translation**: no offline model — falls back to an online endpoint that some
  networks block. English⇄Hindi/Bengali/Urdu/French/German/Spanish work fully offline.
- **AI features** (chat/summarize) require an LLM API key and the AI service is not in the default
  compose stack — wire it up separately if you need it.
