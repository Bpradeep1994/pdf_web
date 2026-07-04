"""support tickets + platform settings (admin panel)

Revision ID: 0007_support_settings
Revises: 0006_rbac_annotations_payments
Create Date: 2026-06-20
"""
from alembic import op

revision = "0007_support_settings"
down_revision = "0006_rbac_annotations_payments"
branch_labels = None
depends_on = None

_UPGRADE = [
    """CREATE TABLE IF NOT EXISTS support_tickets (
        id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        user_id     UUID REFERENCES users(id) ON DELETE SET NULL,
        subject     VARCHAR(255) NOT NULL,
        message     TEXT NOT NULL,
        status      VARCHAR(20) NOT NULL DEFAULT 'open',     -- open | pending | closed
        priority    VARCHAR(20) NOT NULL DEFAULT 'normal',   -- low | normal | high
        assigned_to UUID REFERENCES users(id) ON DELETE SET NULL,
        response    TEXT,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
    )""",
    "CREATE INDEX IF NOT EXISTS ix_support_status ON support_tickets(status, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS ix_support_user ON support_tickets(user_id)",
    """CREATE TABLE IF NOT EXISTS platform_settings (
        key        VARCHAR(100) PRIMARY KEY,
        value      JSONB NOT NULL DEFAULT '{}'::jsonb,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )""",
]

_DOWNGRADE = [
    "DROP TABLE IF EXISTS platform_settings",
    "DROP TABLE IF EXISTS support_tickets",
]


def upgrade() -> None:
    for stmt in _UPGRADE:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in _DOWNGRADE:
        op.execute(stmt)
