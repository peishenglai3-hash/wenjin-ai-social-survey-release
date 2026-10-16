"""add versioned collaboration research artifacts and redacted shares

Revision ID: 20261016_artifacts
Revises: 20261016_wise
Create Date: 2026-10-16
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261016_artifacts"
down_revision: Union[str, Sequence[str], None] = "20261016_wise"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("research_artifacts"):
        op.create_table(
            "research_artifacts",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("artifact_key", sa.String(length=100), nullable=False),
            sa.Column("kind", sa.String(length=40), nullable=False),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("created_by_profile_id", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.ForeignKeyConstraint(["project_id"], ["survey_projects.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["created_by_profile_id"], ["user_profiles.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("project_id", "artifact_key", name="uq_research_artifact_project_key"),
        )
        op.create_index(
            "ix_research_artifacts_project_status",
            "research_artifacts",
            ["project_id", "status"],
        )

    if not inspector.has_table("research_artifact_versions"):
        op.create_table(
            "research_artifact_versions",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("artifact_id", sa.Integer(), nullable=False),
            sa.Column("version_number", sa.Integer(), nullable=False),
            sa.Column("created_by_profile_id", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(length=24), nullable=False),
            sa.Column("redaction_status", sa.String(length=20), nullable=False),
            sa.Column("redacted_content", sa.Text(), nullable=False),
            sa.Column("content_sha256", sa.String(length=64), nullable=False),
            sa.Column("redaction_note", sa.Text(), nullable=False),
            sa.Column("change_summary", sa.Text(), nullable=False),
            sa.Column("idempotency_key", sa.String(length=128), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.ForeignKeyConstraint(["artifact_id"], ["research_artifacts.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["created_by_profile_id"], ["user_profiles.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("artifact_id", "version_number", name="uq_research_artifact_version_number"),
        )
        op.create_index(
            "ix_research_artifact_versions_artifact_created",
            "research_artifact_versions",
            ["artifact_id", "created_at"],
        )
        op.create_index(
            "ix_research_artifact_versions_idempotency",
            "research_artifact_versions",
            ["artifact_id", "idempotency_key"],
        )

    if not inspector.has_table("research_annotations"):
        op.create_table(
            "research_annotations",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("version_id", sa.Integer(), nullable=False),
            sa.Column("author_profile_id", sa.Integer(), nullable=True),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("anchor_start", sa.Integer(), nullable=True),
            sa.Column("anchor_end", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("resolution_note", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.ForeignKeyConstraint(["version_id"], ["research_artifact_versions.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["author_profile_id"], ["user_profiles.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_research_annotations_version_status",
            "research_annotations",
            ["version_id", "status"],
        )

    if not inspector.has_table("research_review_tasks"):
        op.create_table(
            "research_review_tasks",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("version_id", sa.Integer(), nullable=False),
            sa.Column("requested_by_profile_id", sa.Integer(), nullable=True),
            sa.Column("reviewer_profile_id", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(length=24), nullable=False),
            sa.Column("request_note", sa.Text(), nullable=False),
            sa.Column("decision_note", sa.Text(), nullable=False),
            sa.Column("decided_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.ForeignKeyConstraint(["version_id"], ["research_artifact_versions.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["requested_by_profile_id"], ["user_profiles.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["reviewer_profile_id"], ["user_profiles.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_research_review_tasks_version_status",
            "research_review_tasks",
            ["version_id", "status"],
        )

    if not inspector.has_table("research_shares"):
        op.create_table(
            "research_shares",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("version_id", sa.Integer(), nullable=False),
            sa.Column("created_by_profile_id", sa.Integer(), nullable=True),
            sa.Column("token_digest", sa.String(length=64), nullable=False),
            sa.Column("audience", sa.String(length=200), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("revoked_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.ForeignKeyConstraint(["version_id"], ["research_artifact_versions.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["created_by_profile_id"], ["user_profiles.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("token_digest"),
        )
        op.create_index(
            "ix_research_shares_version_status",
            "research_shares",
            ["version_id", "status"],
        )
        op.create_index(
            "ix_research_shares_expires",
            "research_shares",
            ["expires_at", "status"],
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("research_shares"):
        op.drop_index("ix_research_shares_expires", table_name="research_shares")
        op.drop_index("ix_research_shares_version_status", table_name="research_shares")
        op.drop_table("research_shares")
    if inspector.has_table("research_review_tasks"):
        op.drop_index("ix_research_review_tasks_version_status", table_name="research_review_tasks")
        op.drop_table("research_review_tasks")
    if inspector.has_table("research_annotations"):
        op.drop_index("ix_research_annotations_version_status", table_name="research_annotations")
        op.drop_table("research_annotations")
    if inspector.has_table("research_artifact_versions"):
        op.drop_index("ix_research_artifact_versions_idempotency", table_name="research_artifact_versions")
        op.drop_index("ix_research_artifact_versions_artifact_created", table_name="research_artifact_versions")
        op.drop_table("research_artifact_versions")
    if inspector.has_table("research_artifacts"):
        op.drop_index("ix_research_artifacts_project_status", table_name="research_artifacts")
        op.drop_table("research_artifacts")
