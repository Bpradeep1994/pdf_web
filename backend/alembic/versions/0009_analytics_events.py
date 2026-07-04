"""analytics events (admin KPIs: countries, traffic sources)

Revision ID: 0009_analytics_events
Revises: 0008_payments_platform
Create Date: 2026-06-22
"""
from alembic import op

revision = "0009_analytics_events"
down_revision = "0008_payments_platform"
branch_labels = None
depends_on = None

_UPGRADE = [
    """CREATE TABLE IF NOT EXISTS analytics_events (
        id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        user_id     UUID REFERENCES users(id) ON DELETE SET NULL,
        event_type  VARCHAR(40) NOT NULL DEFAULT 'pageview',
        source      VARCHAR(60),                 -- Direct | Google | Social | <referrer host>
        country     VARCHAR(8),                  -- ISO region from visitor locale (IN, US, …)
        path        VARCHAR(255),
        created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
    )""",
    "CREATE INDEX IF NOT EXISTS ix_analytics_created ON analytics_events(created_at DESC)",
    "CREATE INDEX IF NOT EXISTS ix_analytics_country ON analytics_events(country)",
    "CREATE INDEX IF NOT EXISTS ix_analytics_source ON analytics_events(source)",
]


def upgrade() -> None:
    for stmt in _UPGRADE:
        op.execute(stmt)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS analytics_events")
