"""rbac (roles/permissions), annotations, payments

Revision ID: 0006_rbac_annotations_payments
Revises: 0005_soft_delete
Create Date: 2026-06-20
"""
from alembic import op

revision = "0006_rbac_annotations_payments"
down_revision = "0005_soft_delete"
branch_labels = None
depends_on = None

# asyncpg rejects multiple statements per execute() — run them one at a time.
_UPGRADE = [
    """CREATE TABLE IF NOT EXISTS roles (
        id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        name        VARCHAR(50) UNIQUE NOT NULL,
        description TEXT,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
    )""",
    """CREATE TABLE IF NOT EXISTS permissions (
        id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        name        VARCHAR(100) UNIQUE NOT NULL,
        description TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS role_permissions (
        role_id       UUID NOT NULL REFERENCES roles(id)       ON DELETE CASCADE,
        permission_id UUID NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
        PRIMARY KEY (role_id, permission_id)
    )""",
    """CREATE TABLE IF NOT EXISTS user_roles (
        user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        role_id    UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
        granted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        PRIMARY KEY (user_id, role_id)
    )""",
    "CREATE INDEX IF NOT EXISTS ix_user_roles_user ON user_roles(user_id)",
    """CREATE TABLE IF NOT EXISTS annotations (
        id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        document_id  UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
        user_id      UUID REFERENCES users(id) ON DELETE SET NULL,
        page_number  INT NOT NULL DEFAULT 1,
        type         VARCHAR(30) NOT NULL,
        color        VARCHAR(16),
        x            DOUBLE PRECISION,
        y            DOUBLE PRECISION,
        width        DOUBLE PRECISION,
        height       DOUBLE PRECISION,
        data         JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
    )""",
    "CREATE INDEX IF NOT EXISTS ix_annotations_doc ON annotations(document_id, page_number)",
    """CREATE TABLE IF NOT EXISTS payments (
        id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        user_id           UUID REFERENCES users(id) ON DELETE SET NULL,
        subscription_id   UUID REFERENCES subscriptions(id) ON DELETE SET NULL,
        invoice_id        UUID REFERENCES invoices(id) ON DELETE SET NULL,
        stripe_payment_id VARCHAR(255) UNIQUE,
        amount_cents      BIGINT NOT NULL DEFAULT 0,
        currency          VARCHAR(8) NOT NULL DEFAULT 'usd',
        status            VARCHAR(30) NOT NULL DEFAULT 'pending',
        created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
    )""",
    "CREATE INDEX IF NOT EXISTS ix_payments_user ON payments(user_id)",
]

_DOWNGRADE = [
    "DROP TABLE IF EXISTS payments",
    "DROP TABLE IF EXISTS annotations",
    "DROP TABLE IF EXISTS user_roles",
    "DROP TABLE IF EXISTS role_permissions",
    "DROP TABLE IF EXISTS permissions",
    "DROP TABLE IF EXISTS roles",
]


def upgrade() -> None:
    for stmt in _UPGRADE:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in _DOWNGRADE:
        op.execute(stmt)
