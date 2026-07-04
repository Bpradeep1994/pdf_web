"""baseline — adopts the canonical SQL schema (database/migrations/001_init.sql)

Revision ID: 0001_baseline
Revises:
Create Date: 2026-06-20

This is a MARKER revision. The initial schema (enums, tables, triggers) is provisioned
by `database/migrations/001_init.sql` — applied automatically on Postgres first-init
locally, and via a one-time bootstrap on managed DBs (see docs/DEPLOYMENT.md).

Adoption on an existing database:
    alembic stamp 0001_baseline

New schema changes from here on get their own revisions:
    alembic revision -m "add X"   # then hand-write upgrade()/downgrade()
    alembic upgrade head
"""
revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # No-op: baseline schema is owned by database/migrations/001_init.sql.
    pass


def downgrade() -> None:
    pass
