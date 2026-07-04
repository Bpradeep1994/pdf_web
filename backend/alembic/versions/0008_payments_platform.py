"""payments platform: methods, refunds, events; subscription + payment columns

Revision ID: 0008_payments_platform
Revises: 0007_support_settings
Create Date: 2026-06-22
"""
from alembic import op

revision = "0008_payments_platform"
down_revision = "0007_support_settings"
branch_labels = None
depends_on = None

_UPGRADE = [
    # subscriptions: provider, lifetime flag, cancel-at-period-end (interval/trial_end already exist)
    "ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS provider VARCHAR(20) NOT NULL DEFAULT 'manual'",
    "ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS lifetime BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS cancel_at_period_end BOOLEAN NOT NULL DEFAULT FALSE",
    # payments: provider / method / card brand
    "ALTER TABLE payments ADD COLUMN IF NOT EXISTS provider VARCHAR(20)",
    "ALTER TABLE payments ADD COLUMN IF NOT EXISTS method VARCHAR(30)",
    "ALTER TABLE payments ADD COLUMN IF NOT EXISTS card_brand VARCHAR(30)",
    "ALTER TABLE payments ADD COLUMN IF NOT EXISTS description TEXT",
    # saved payment methods
    """CREATE TABLE IF NOT EXISTS payment_methods (
        id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        provider    VARCHAR(20) NOT NULL,            -- stripe|paypal|razorpay|applepay|googlepay
        type        VARCHAR(30) NOT NULL,            -- card|upi|netbanking|wallet|paypal
        brand       VARCHAR(30),                     -- visa|mastercard|amex|discover|jcb|diners
        last4       VARCHAR(8),
        exp_month   INT,
        exp_year    INT,
        is_default  BOOLEAN NOT NULL DEFAULT FALSE,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
    )""",
    "CREATE INDEX IF NOT EXISTS ix_payment_methods_user ON payment_methods(user_id)",
    # refunds
    """CREATE TABLE IF NOT EXISTS refunds (
        id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        payment_id   UUID REFERENCES payments(id) ON DELETE SET NULL,
        user_id      UUID REFERENCES users(id) ON DELETE SET NULL,
        amount_cents BIGINT NOT NULL DEFAULT 0,
        currency     VARCHAR(8) NOT NULL DEFAULT 'usd',
        reason       TEXT,
        status       VARCHAR(20) NOT NULL DEFAULT 'succeeded',
        provider     VARCHAR(20),
        created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
    )""",
    "CREATE INDEX IF NOT EXISTS ix_refunds_user ON refunds(user_id)",
    # payment audit trail
    """CREATE TABLE IF NOT EXISTS payment_events (
        id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        user_id      UUID REFERENCES users(id) ON DELETE SET NULL,
        provider     VARCHAR(20),
        event_type   VARCHAR(50) NOT NULL,           -- payment.succeeded|refund|subscription.changed|...
        amount_cents BIGINT,
        currency     VARCHAR(8),
        data         JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
    )""",
    "CREATE INDEX IF NOT EXISTS ix_payment_events_user ON payment_events(user_id, created_at DESC)",
]

_DOWNGRADE = [
    "DROP TABLE IF EXISTS payment_events",
    "DROP TABLE IF EXISTS refunds",
    "DROP TABLE IF EXISTS payment_methods",
    "ALTER TABLE payments DROP COLUMN IF EXISTS description",
    "ALTER TABLE payments DROP COLUMN IF EXISTS card_brand",
    "ALTER TABLE payments DROP COLUMN IF EXISTS method",
    "ALTER TABLE payments DROP COLUMN IF EXISTS provider",
    "ALTER TABLE subscriptions DROP COLUMN IF EXISTS cancel_at_period_end",
    "ALTER TABLE subscriptions DROP COLUMN IF EXISTS lifetime",
    "ALTER TABLE subscriptions DROP COLUMN IF EXISTS provider",
]


def upgrade() -> None:
    for stmt in _UPGRADE:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in _DOWNGRADE:
        op.execute(stmt)
