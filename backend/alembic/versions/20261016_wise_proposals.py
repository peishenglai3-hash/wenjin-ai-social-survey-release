"""add reviewable WISE proposal and memory-promotion records

Revision ID: 20261016_wise
Revises: 20261016_request_audit
Create Date: 2026-10-16
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261016_wise"
down_revision: Union[str, Sequence[str], None] = "20261016_request_audit"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("wise_proposals"):
        return
    op.create_table(
        "wise_proposals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("proposal_text", sa.Text(), nullable=False),
        sa.Column("candidate_memory_json", sa.Text(), nullable=False),
        sa.Column("evidence_refs_json", sa.Text(), nullable=False),
        sa.Column("applicability", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("counterexamples", sa.Text(), nullable=False),
        sa.Column("side_effects", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=False),
        sa.Column("approved_by_profile_id", sa.Integer(), nullable=True),
        sa.Column("approved_memory_id", sa.Integer(), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["user_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["survey_projects.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["approved_by_profile_id"], ["user_profiles.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["approved_memory_id"], ["user_memories.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_wise_proposals_profile_status",
        "wise_proposals",
        ["profile_id", "status"],
    )
    op.create_index("ix_wise_proposals_project", "wise_proposals", ["project_id"])
    op.create_index(
        "ix_wise_proposals_profile_idempotency",
        "wise_proposals",
        ["profile_id", "idempotency_key"],
    )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("wise_proposals"):
        return
    op.drop_index("ix_wise_proposals_profile_idempotency", table_name="wise_proposals")
    op.drop_index("ix_wise_proposals_project", table_name="wise_proposals")
    op.drop_index("ix_wise_proposals_profile_status", table_name="wise_proposals")
    op.drop_table("wise_proposals")
