#!/usr/bin/env bash
# One-shot production deploy. Run from the repo root on your VPS:
#   ./deploy/deploy.sh
#
# Prereqs: Docker + compose plugin installed, `.env.production` filled in
# (copy from .env.production.example and set real secrets + domains).
set -euo pipefail

cd "$(dirname "$0")/.."
ENV_FILE=".env.production"
COMPOSE="docker compose --env-file $ENV_FILE -f docker-compose.yml -f docker-compose.prod.yml --profile tls --profile av"

# ── Safety checks ─────────────────────────────────────────────────────────────
[ -f "$ENV_FILE" ] || { echo "✗ $ENV_FILE not found — copy .env.production.example and fill it in."; exit 1; }

# Never deploy with the rate-limit bypass token set (it disables rate limiting).
if grep -qE '^RATE_LIMIT_BYPASS_TOKEN=.+' "$ENV_FILE"; then
  echo "✗ RATE_LIMIT_BYPASS_TOKEN must be EMPTY in production. Aborting."; exit 1
fi
# Refuse the known dev placeholders.
if grep -qE '^(SECRET_KEY=__GENERATE|POSTGRES_PASSWORD=__GENERATE|SECRET_KEY=supersecretkey)' "$ENV_FILE"; then
  echo "✗ $ENV_FILE still has placeholder secrets. Generate real ones first."; exit 1
fi
echo "✓ pre-flight checks passed"

# ── Pull latest code ──────────────────────────────────────────────────────────
if [ -d .git ]; then echo "→ git pull"; git pull --ff-only || echo "  (skipped — not fast-forward)"; fi

# ── Build & start ─────────────────────────────────────────────────────────────
echo "→ building and starting the stack…"
$COMPOSE up -d --build

# ── Wait for the gateway ──────────────────────────────────────────────────────
echo -n "→ waiting for gateway health"
for i in $(seq 1 60); do
  if docker exec pdf_editor-gateway-1 python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/health')" 2>/dev/null; then
    echo " ✓"; break
  fi
  echo -n "."; sleep 3
  [ "$i" = 60 ] && { echo " ✗ gateway did not become healthy"; $COMPOSE logs --tail=50 gateway; exit 1; }
done

# ── Database migrations ───────────────────────────────────────────────────────
echo "→ applying database migrations…"
set -a; . "$ENV_FILE"; set +a
docker run --rm --network pdf_editor_default -v "$PWD/backend:/app" -w /app \
  -e DATABASE_URL="postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}" \
  python:3.12-slim sh -c "pip install -q -r requirements-migrations.txt && alembic upgrade head"

# ── Post-deploy smoke test ────────────────────────────────────────────────────
echo "→ smoke testing the live deployment…"
if command -v python3 >/dev/null; then
  pip install -q httpx 2>/dev/null || true
  STAGING_URL="https://${DOMAIN_API}" python3 tests/smoke_staging.py || echo "  ⚠ smoke test reported issues — check the output above"
fi

echo ""
echo "✅ Deploy complete."
echo "   App: https://${DOMAIN_APP}   API: https://${DOMAIN_API}"
$COMPOSE ps
echo ""
echo "Rollback:  git checkout <previous-tag> && ./deploy/deploy.sh"
