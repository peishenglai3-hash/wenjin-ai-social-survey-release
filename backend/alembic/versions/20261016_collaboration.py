"""add collaboration membership, invitations, and audit metadata

Revision ID: 20261016_collaboration
Revises: 20261016_questionnaire
Create Date: 2026-10-16
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261016_collaboration"
down_revision: Union[str, Sequence[str], None] = "20261016_questionnaire"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _timestamp_columns() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "project_members",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("invited_by_profile_id", sa.Integer(), nullable=True),
        *_timestamp_columns(),
        sa.ForeignKeyConstraint(["project_id"], ["survey_projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["profile_id"], ["user_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invited_by_profile_id"], ["user_profiles.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "profile_id", name="uq_project_member_project_profile"),
    )
    op.create_index("ix_project_members_project_status", "project_members", ["project_id", "status"])

    op.create_table(
        "project_invitations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("invitee_profile_id", sa.Integer(), nullable=False),
        sa.Column("inviter_profile_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("accepted_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        *_timestamp_columns(),
        sa.ForeignKeyConstraint(["project_id"], ["survey_projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invitee_profile_id"], ["user_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["inviter_profile_id"], ["user_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_project_invitations_invitee_status",
        "project_invitations",
        ["invitee_profile_id", "status"],
    )
    op.create_index(
        "ix_project_invitations_project_status",
        "project_invitations",
        ["project_id", "status"],
    )

    op.create_table(
        "project_audit_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("actor_profile_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("target_type", sa.String(length=50), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=True),
        sa.Column("details_json", sa.Text(), nullable=False),
        *_timestamp_columns(),
        sa.ForeignKeyConstraint(["project_id"], ["survey_projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_profile_id"], ["user_profiles.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_project_audit_events_project_created",
        "project_audit_events",
        ["project_id", "created_at"],
    )

    # Preserve the owner invariant for projects that predate this migration.
    op.execute(
        """
        INSERT INTO project_members
            (project_id, profile_id, role, status, created_at, updated_at)
        SELECT p.id, p.profile_id, 'owner', 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        FROM survey_projects p
        WHERE NOT EXISTS (
            SELECT 1 FROM project_members m
            WHERE m.project_id = p.id AND m.profile_id = p.profile_id
        )
        """
    )


def downgrade() -> None:
    op.drop_index("ix_project_audit_events_project_created", table_name="project_audit_events")
    op.drop_table("project_audit_events")
    op.drop_index("ix_project_invitations_project_status", table_name="project_invitations")
    op.drop_index("ix_project_invitations_invitee_status", table_name="project_invitations")
    op.drop_table("project_invitations")
    op.drop_index("ix_project_members_project_status", table_name="project_members")
    op.drop_table("project_members")

