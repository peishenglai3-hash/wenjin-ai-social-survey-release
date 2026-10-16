"""add owned upload registry and retention metadata

Revision ID: 20261016_uploads
Revises: 20261016_skill_fields
Create Date: 2026-10-16
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261016_uploads"
down_revision: Union[str, Sequence[str], None] = "20261016_skill_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "uploaded_files",
        sa.Column("file_id", sa.String(length=32), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("storage_name", sa.String(length=128), nullable=False),
        sa.Column("suffix", sa.String(length=12), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["user_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("file_id"),
        sa.UniqueConstraint("storage_name"),
    )
    op.create_index(
        "ix_uploaded_files_profile_expires",
        "uploaded_files",
        ["profile_id", "expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_uploaded_files_profile_expires", table_name="uploaded_files")
    op.drop_table("uploaded_files")
