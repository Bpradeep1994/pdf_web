"""Widen users.mfa_secret to TEXT — the Fernet-encrypted secret ('enc:' + ciphertext)
is ~140 chars, so VARCHAR(64) made /auth/mfa/setup fail with StringDataRightTruncation.

Revision ID: 0011_widen_mfa_secret
Revises: 0010_user_admin_roles
Create Date: 2026-07-02
"""
from alembic import op

revision = "0011_widen_mfa_secret"
down_revision = "0010_user_admin_roles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ALTER COLUMN mfa_secret TYPE TEXT")


def downgrade() -> None:
    # values longer than 64 chars would be lost; truncate deliberately
    op.execute("ALTER TABLE users ALTER COLUMN mfa_secret TYPE VARCHAR(64) USING left(mfa_secret, 64)")
