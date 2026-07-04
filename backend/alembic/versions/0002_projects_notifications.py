"""projects / team workspaces + notifications

Revision ID: 0002_projects_notifications
Revises: 0001_baseline
Create Date: 2026-06-20
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0002_projects_notifications"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None

UUID = pg.UUID(as_uuid=True)
NOW  = sa.text("now()")
GEN  = sa.text("uuid_generate_v4()")


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", UUID, primary_key=True, server_default=GEN),
        sa.Column("owner_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW),
    )
    op.create_table(
        "project_members",
        sa.Column("id", UUID, primary_key=True, server_default=GEN),
        sa.Column("project_id", UUID, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("role", sa.String(16), nullable=False, server_default="viewer"),  # owner|editor|viewer
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW),
        sa.UniqueConstraint("project_id", "user_id", name="uq_project_member"),
    )
    op.create_table(
        "project_documents",
        sa.Column("id", UUID, primary_key=True, server_default=GEN),
        sa.Column("project_id", UUID, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("document_id", UUID, sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("added_at", sa.DateTime(timezone=True), server_default=NOW),
        sa.UniqueConstraint("project_id", "document_id", name="uq_project_document"),
    )
    op.create_table(
        "notifications",
        sa.Column("id", UUID, primary_key=True, server_default=GEN),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body", sa.Text()),
        sa.Column("link", sa.Text()),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, index=True),
    )


def downgrade() -> None:
    for tbl in ("notifications", "project_documents", "project_members", "projects"):
        op.drop_table(tbl)
