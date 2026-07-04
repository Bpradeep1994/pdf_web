# Self-Hosted Deployment (no cloud account required)

The whole platform runs on a single machine with Docker Compose — **MinIO** replaces AWS S3,
and Postgres / Redis / RabbitMQ all run locally. No AWS/GCP/Azure account needed. For a public
site you only need **one VM/VPS** and (optionally) a **domain name** for real HTTPS.

## 1. Run it locally

```bash
cp .env.example .env          # then edit: set a strong SECRET_KEY, passwords
docker compose up -d          # builds + starts the 10-service stack
# App:  http://localhost:3000     API: http://localhost:8000
# MinIO console: http://localhost:9001   RabbitMQ: http://localhost:15672
```

Apply DB migrations (the canonical schema auto-loads on first init; for upgrades):
```bash
docker run --rm --network pdf_editor_default -v "$PWD/backend:/app" -w /app \
  -e DATABASE_URL=postgresql+asyncpg://pdfuser:pdfpass@postgres:5432/pdfeditor \
  python:3.12-slim sh -c "pip install -q -r requirements-migrations.txt && alembic upgrade head"
```

## 2. HTTPS (no cloud) — Caddy profile

```bash
docker compose --profile tls up -d caddy      # https://localhost (self-signed)
```
For a **public domain**: point its DNS A-record at your server, open ports 80/443, edit
`deploy/caddy/Caddyfile` (uncomment the `api.` / `app.` blocks, set `ACME_EMAIL`), and Caddy
auto-provisions + renews **Let's Encrypt** certificates. No cloud account, no manual certs.

## 3. Monitoring — Prometheus + Grafana profile

```bash
docker compose --profile monitoring up -d
# Prometheus: http://localhost:9090   Grafana: http://localhost:3001 (anon enabled)
```
Gateway metrics are scraped from `/metrics`; alert rules live in `monitoring/alerts.yml`.
(Opt-in so they don't consume RAM on small hosts.)

## 4. Backups (cron on the host)

```bash
# every 6h — keeps 30 days locally; set BACKUP_BUCKET to also push to S3/MinIO
0 */6 * * * DATABASE_URL_PSQL=postgresql://pdfuser:pdfpass@localhost:5432/pdfeditor \
            BACKUP_DIR=/var/backups/pdfforge bash /opt/pdfforge/backend/scripts/backup.sh
```
Restore + DR procedure: see `docs/DR_RUNBOOK.md`.

## 5. Production checklist (single VM, no cloud)

- [ ] Strong `SECRET_KEY`, `ENVIRONMENT=production` (auth fails-closed on weak secrets)
- [ ] Real passwords for Postgres/Redis/RabbitMQ/MinIO in `.env` (never commit it)
- [ ] `ALLOWED_ORIGINS` = your domain; `NEXT_PUBLIC_API_URL` = `https://api.yourdomain`
- [ ] Caddy TLS profile enabled with your domain (auto Let's Encrypt)
- [ ] Monitoring profile enabled + alert receiver (email/Slack) configured in Prometheus Alertmanager
- [ ] `backup.sh` scheduled + a **test restore** performed (see DR runbook)
- [ ] Set MinIO to a dedicated data disk with backups, or point S3_* at a managed/object store
- [ ] (Optional) OAuth + Stripe keys in `.env` to enable social login + paid plans

## Hardware guidance

The dev box used here (5.9 GB RAM) runs the stack but is tight (LibreOffice/OCR are memory-heavy).
For production self-hosting, use **≥ 8 GB RAM / 4 vCPU**; scale the `pdf_service`, `ocr_service`,
and `conversion_service` (the CPU/RAM-heavy ones) horizontally with `docker compose up --scale`
behind Caddy, or move to the provided Helm chart if you later adopt Kubernetes.
