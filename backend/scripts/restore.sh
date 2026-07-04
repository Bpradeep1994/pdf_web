#!/usr/bin/env bash
# Restore Postgres from a pg_dump custom-format file (local path or s3:// URI).
#   ./restore.sh /backups/pdfeditor_20260620_010000.dump
#   ./restore.sh s3://my-bucket/db/pdfeditor_20260620_010000.dump
# DATABASE_URL_PSQL must be libpq format. THIS IS DESTRUCTIVE (--clean).
set -euo pipefail

SRC=${1:?usage: restore.sh <dump-file|s3-uri>}
if [[ "$SRC" == s3://* ]]; then
  echo "[restore] downloading $SRC"
  aws s3 cp "$SRC" /tmp/restore.dump
  SRC=/tmp/restore.dump
fi

echo "[restore] restoring into ${DATABASE_URL_PSQL:?set DATABASE_URL_PSQL} (clean)"
pg_restore --clean --if-exists --no-owner --no-privileges -d "$DATABASE_URL_PSQL" "$SRC"
echo "[restore] done. Verify app health + alembic current."
