# Disaster Recovery Runbook

**Targets:** RTO ≤ 1 hour · RPO ≤ 6 hours (tighten to ≤ 5 min with RDS PITR).

## Backups
- **Database**: `backend/scripts/backup.sh` via cron / k8s CronJob every 6h →
  `pg_dump -Fc` uploaded to `s3://$BACKUP_BUCKET/db/`. In AWS, also enable **RDS automated
  snapshots + Point-In-Time Recovery** (RPO ≈ 5 min) — the script is the portable fallback.
- **Object storage**: enable **S3 versioning** + a lifecycle rule (e.g. expire noncurrent
  versions after 90d, transition to Glacier). Document versions are already retained in
  `document_versions`, and deletes are **soft** (`documents.deleted_at`) so accidental deletes
  are recoverable in-app.
- **Schema**: managed by Alembic (`alembic upgrade head`); migrations are in version control.

## Restore
1. Provision a fresh DB (RDS or container).
2. `DATABASE_URL_PSQL=postgresql://… backend/scripts/restore.sh s3://$BACKUP_BUCKET/db/<dump>`
   (or restore from an RDS snapshot / PITR for a tighter RPO).
3. `alembic upgrade head` to confirm schema head; check `alembic current`.
4. Point services at the restored DB; roll pods; verify `/health` on every service.
5. S3: objects persist independently; if a bucket was lost, restore from versioning/replication.

## Failure scenarios
| Failure | Action |
|---|---|
| App pod crash | k8s restarts (liveness/readiness on `/health`); HPA keeps capacity |
| DB outage | RDS Multi-AZ auto-failover; else restore from snapshot/PITR (RTO ≤ 1h) |
| Redis outage | App fails-open for rate-limit/lockout (degraded, not down); ElastiCache Multi-AZ for HA |
| RabbitMQ outage | Jobs queue/retry; Amazon MQ active/standby; workers reconnect |
| Region outage | Restore in a second region from S3 backups + snapshot copy (manual DR, RTO hours) |

## DR drills
Run a restore into a staging DB **quarterly**; record actual RTO/RPO. Restore is unverified
until it has been drilled.
