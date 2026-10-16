"""add fields required by the existing skill marketplace routes

Revision ID: 20261016_skill_fields
Revises: 20261016_knowledge
Create Date: 2026-10-16
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261016_skill_fields"
down_revision: Union[str, Sequence[str], None] = "20261016_knowledge"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_COLUMNS = {
    "published_at": sa.Column("published_at", sa.DateTime(), nullable=True),
    "published_version": sa.Column("published_version", sa.String(length=30), server_default="1.0.0", nullable=False),
    "fork_count": sa.Column("fork_count", sa.Integer(), server_default="0", nullable=False),
    "rating_avg": sa.Column("rating_avg", sa.Float(), server_default="0", nullable=False),
    "rating_count": sa.Column("rating_count", sa.Integer(), server_default="0", nullable=False),
    "download_count": sa.Column("download_count", sa.Integer(), server_default="0", nullable=False),
    "readme": sa.Column("readme", sa.Text(), nullable=True),
    "example_input": sa.Column("example_input", sa.Text(), nullable=True),
    "example_output": sa.Column("example_output", sa.Text(), nullable=True),
    "compatible_models": sa.Column("compatible_models", sa.String(length=1000), server_default="[]", nullable=False),
    "min_app_version": sa.Column("min_app_version", sa.String(length=30), server_default="0.2.0", nullable=False),
    "forked_from_id": sa.Column("forked_from_id", sa.Integer(), nullable=True),
    "fork_lineage": sa.Column("fork_lineage", sa.String(length=2000), server_default="[]", nullable=False),
}


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = {column["name"] for column in inspector.get_columns("user_skills")}
    for name, column in _COLUMNS.items():
        if name not in existing:
            op.add_column("user_skills", column)


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = {column["name"] for column in inspector.get_columns("user_skills")}
    for name in reversed(tuple(_COLUMNS)):
        if name in existing:
            op.drop_column("user_skills", name)
