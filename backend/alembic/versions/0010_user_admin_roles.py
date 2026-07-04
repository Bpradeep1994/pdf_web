"""user admin_level (access roles) + status (suspend/ban)

Revision ID: 0010_user_admin_roles
Revises: 0009_analytics_events
Create Date: 2026-06-22
"""
from alembic import op

revision = "0010_user_admin_roles"
down_revision = "0009_analytics_events"
branch_labels = None
depends_on = None

_UPGRADE = [
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS admin_level VARCHAR(20) NOT NULL DEFAULT 'user'",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'active'",
    # existing platform admins (role enum) become super admins so they keep panel access
    "UPDATE users SET admin_level = 'superadmin' WHERE role = 'admin'",
    "CREATE INDEX IF NOT EXISTS ix_users_admin_level ON users(admin_level)",
]

_DOWNGRADE = [
    "ALTER TABLE users DROP COLUMN IF EXISTS status",
    "ALTER TABLE users DROP COLUMN IF EXISTS admin_level",
]


def upgrade() -> None:
    for stmt in _UPGRADE:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in _DOWNGRADE:
        op.execute(stmt)
