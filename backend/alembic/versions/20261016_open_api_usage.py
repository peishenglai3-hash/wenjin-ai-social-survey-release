"""add privacy-safe Open API quota usage records

Revision ID: 20261016_open_api_usage
Revises: 20261016_artifacts
Create Date: 2026-10-16
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261016_open_api_usage"
down_revision: Union[str, Sequence[str], None] = "20261016_artifacts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("open_api_usage_records"):
        return
    op.create_table(
        "open_api_usage_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error_category", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["user_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_open_api_usage_profile_created",
        "open_api_usage_records",
        ["profile_id", "created_at"],
    )
    op.create_index("ix_open_api_usage_request", "open_api_usage_records", ["request_id"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("open_api_usage_records"):
        return
    op.drop_index("ix_open_api_usage_request", table_name="open_api_usage_records")
    op.drop_index("ix_open_api_usage_profile_created", table_name="open_api_usage_records")
    op.drop_table("open_api_usage_records")
