"""soft delete: documents.deleted_at

Revision ID: 0005_soft_delete
Revises: 0004_folders
Create Date: 2026-06-20
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_soft_delete"
down_revision = "0004_folders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_documents_deleted_at", "documents", ["deleted_at"])


def downgrade() -> None:
    op.drop_index("ix_documents_deleted_at", table_name="documents")
    op.drop_column("documents", "deleted_at")
