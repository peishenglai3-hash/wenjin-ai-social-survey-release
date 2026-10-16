"""add request correlation ids to collaboration audit events

Revision ID: 20261016_request_audit
Revises: 20261016_uploads
Create Date: 2026-10-16
"""

from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa


revision: str = "20261016_request_audit"
down_revision: Union[str, Sequence[str], None] = "20261016_uploads"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if context.is_offline_mode():
        columns: set[str] = set()
    else:
        columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("project_audit_events")}
    if "request_id" not in columns:
        op.add_column("project_audit_events", sa.Column("request_id", sa.String(length=128), nullable=True))


def downgrade() -> None:
    if context.is_offline_mode():
        columns: set[str] = set()
    else:
        columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("project_audit_events")}
    if "request_id" in columns:
        op.drop_column("project_audit_events", "request_id")
