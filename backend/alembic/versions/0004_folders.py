"""folders + documents.folder_id

Revision ID: 0004_folders
Revises: 0003_api_keys
Create Date: 2026-06-20
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0004_folders"
down_revision = "0003_api_keys"
branch_labels = None
depends_on = None

UUID = pg.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "folders",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("owner_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("parent_id", UUID, sa.ForeignKey("folders.id", ondelete="CASCADE"), index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.add_column("documents", sa.Column(
        "folder_id", UUID, sa.ForeignKey("folders.id", ondelete="SET NULL"), nullable=True, index=True))


def downgrade() -> None:
    op.drop_column("documents", "folder_id")
    op.drop_table("folders")
