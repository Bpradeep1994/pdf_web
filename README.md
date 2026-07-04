# PDF Editor — AI-Powered Document Platform

A full-stack, microservices PDF platform: edit, sign, convert, compress, OCR, translate,
and manage PDFs in the browser. FastAPI backend, Next.js frontend, containerised with
Docker, deployable to Kubernetes.

<!-- Enable GitHub Actions to activate this badge -->
![CI](https://github.com/Bpradeep1994/pdf_web/actions/workflows/ci.yml/badge.svg)

---

## Features

**Editing** — add / edit / delete text in place, highlight, redact, freehand draw, insert &
crop images, shapes, watermarks, with keyboard **undo/redo** (Ctrl+Z / Ctrl+Y) backed by full
version history.

**Pages** — add, delete, duplicate, extract, rotate, and rearrange pages; merge and split PDFs.

**Convert** — PDF ⇄ Word / Excel / PowerPoint / images, plus HTML → PDF and image/Office → PDF.

**Compress** — three quality presets with real image recompression and a reported savings ratio.

**Translate** — in-place, layout-preserving translation (English ⇄ Hindi, Bengali, Urdu, French,
German, Spanish offline via LibreTranslate; more via fallback).

**Sign** — draw or upload a signature, save & reuse it, or send signature requests. OCR makes
scanned documents searchable.

**Accounts & billing** — JWT auth with refresh rotation, MFA (TOTP), OAuth (Google/GitHub/
Microsoft), brute-force lockout, Stripe billing (+ demo mode), an admin panel, folders/projects,
notifications, and per-plan storage quotas.

## Architecture

A gateway fronts six services; infrastructure runs as separate containers.

```
                    ┌──────────────┐
  Browser  ───────► │   Gateway    │  :8000   (routing, auth, rate-limit, WebSocket)
                    └──────┬───────┘
        ┌──────────────────┼───────────────────────────────┐
        ▼                  ▼                ▼               ▼
   auth_service      pdf_service     ocr_service    conversion_service
     :8001             :8002            :8004            :8005
  (users, billing,  (edit, pages,   (searchable     (convert, protect,
   admin, MFA)       versions,        text)           translate, scan)
                     signatures)
        └──────────────────┬───────────────────────────────┘
                           ▼
     Postgres · Redis · RabbitMQ · MinIO (S3) · LibreTranslate
```

Frontend: **Next.js 14** (App Router) + Tailwind, served at `:3000`.

## Tech stack

| Layer | Tech |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy (async), PyMuPDF, Alembic |
| Frontend | Next.js 14, React 18, TypeScript, Tailwind, fabric.js, pdf.js |
| Data | PostgreSQL, Redis, RabbitMQ, MinIO (S3-compatible) |
| Infra | Docker Compose, Kubernetes (Helm), Caddy (TLS), Prometheus/Grafana |
| Testing | pytest, Playwright, axe-core (a11y), k6 (load) |

## Quick start (local)

Requires Docker.

```bash
git clone https://github.com/Bpradeep1994/pdf_web.git
cd pdf_web
cp .env.example .env
docker compose up -d --build
```

- App: http://localhost:3000
- API gateway: http://localhost:8000
- MinIO console: http://localhost:9001 · RabbitMQ: http://localhost:15672

## Testing

```bash
# Backend integration suite (needs the stack running)
pip install pytest httpx
pytest tests -m integration

# Frontend E2E + accessibility (Chromium)
cd frontend && npm ci && npx playwright test --project=chromium

# Load benchmark
docker run --rm --network pdf_editor_default -e BASE=http://gateway:8000 \
  -v "$PWD/tests/load:/s" grafana/k6 run /s/benchmark.js
```

## CI/CD

`.github/workflows/ci.yml` runs on every PR: **lint → unit → integration → E2E →
security scans → performance benchmark → deploy-to-staging → post-deploy smoke**
(deploy stages activate when cluster secrets are configured). Enable GitHub Actions
in the repo settings to turn it on.

## Deployment

Follow the **[Launch Runbook → docs/LAUNCH.md](docs/LAUNCH.md)** — a single top-to-bottom
checklist that ties together deployment, payments, and the global edge. Supporting docs:
[GO_LIVE.md](docs/GO_LIVE.md) (VPS/Helm deploy), [PAYMENTS.md](docs/PAYMENTS.md) (Razorpay),
[CLOUDFLARE.md](docs/CLOUDFLARE.md) (global TLS/CDN). Deploy is one command once configured:

```bash
./deploy/deploy.sh
```

## Project status & known limitations

This is a feature-complete, well-tested codebase running in a **development configuration**.
Before a public launch you must supply real secrets, a transactional email provider, live
Stripe keys, and real infrastructure — see the go-live runbook. Additional notes:

- **Browser support:** automated tests cover Chromium (desktop + mobile viewport). Safari/Firefox
  are not yet verified.
- **Compliance:** not SOC 2 / GDPR *certified* — add real certification before claiming it.
- **AI features** (chat-with-PDF, summarize) exist in `backend/ai_service` but are not in the
  default compose stack and require an LLM API key.

## Repository layout

```
backend/     gateway + auth/pdf/ocr/conversion/ai services, shared libs, migrations
frontend/    Next.js app (app router, components, e2e tests)
tests/       pytest integration suites, k6 load, staging smoke
deploy/      Helm chart, Caddy config
kubernetes/  raw K8s manifests
docs/        architecture, deployment, go-live, performance
```
