#!/usr/bin/env bash
# Postgres + (optional) S3 backup. Schedule via cron / k8s CronJob (e.g. every 6h).
# Requires: pg_dump (libpq), aws cli. DATABASE_URL_PSQL must be libpq format:
#   postgresql://USER:PASS@HOST:5432/pdfeditor
set -euo pipefail

TS=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR=${BACKUP_DIR:-/backups}
RETAIN_DAYS=${RETAIN_DAYS:-30}
mkdir -p "$BACKUP_DIR"
OUT="$BACKUP_DIR/pdfeditor_${TS}.dump"

echo "[backup] pg_dump -> $OUT"
pg_dump "${DATABASE_URL_PSQL:?set DATABASE_URL_PSQL}" -Fc -f "$OUT"

if [[ -n "${BACKUP_BUCKET:-}" ]]; then
  echo "[backup] uploading to s3://$BACKUP_BUCKET/db/"
  aws s3 cp "$OUT" "s3://$BACKUP_BUCKET/db/pdfeditor_${TS}.dump"
fi

# prune old local dumps
find "$BACKUP_DIR" -name 'pdfeditor_*.dump' -mtime +"$RETAIN_DAYS" -delete || true
echo "[backup] done."
