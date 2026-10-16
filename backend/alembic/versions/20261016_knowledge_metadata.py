"""store approved knowledge card context metadata

Revision ID: 20261016_knowledge_metadata
Revises: 20261016_open_api_usage
Create Date: 2026-10-16
"""

from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa


revision: str = "20261016_knowledge_metadata"
down_revision: Union[str, Sequence[str], None] = "20261016_open_api_usage"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _existing_columns() -> set[str]:
    if context.is_offline_mode():
        return set()
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns("reference_cards")}


def upgrade() -> None:
    # The preceding knowledge migration creates this table on a clean offline
    # revision chain. Existing online databases still get the table guard.
    if not context.is_offline_mode() and not sa.inspect(op.get_bind()).has_table("reference_cards"):
        return
    columns = _existing_columns()
    additions = (
        ("language", sa.String(length=12)),
        ("field_context", sa.JSON()),
        ("method_tags", sa.JSON()),
        ("material_type", sa.String(length=30)),
    )
    for name, column_type in additions:
        if name not in columns:
            op.add_column("reference_cards", sa.Column(name, column_type, nullable=True))


def downgrade() -> None:
    if context.is_offline_mode() or not sa.inspect(op.get_bind()).has_table("reference_cards"):
        return
    columns = _existing_columns()
    for name in ("material_type", "method_tags", "field_context", "language"):
        if name in columns:
            op.drop_column("reference_cards", name)
