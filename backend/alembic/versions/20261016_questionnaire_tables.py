"""add structured questionnaire tables

Revision ID: 20261016_questionnaire
Revises: 75116760b940
Create Date: 2026-10-16
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261016_questionnaire"
down_revision: Union[str, Sequence[str], None] = "75116760b940"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "questionnaires",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("constructs_json", sa.Text(), nullable=False),
        sa.Column("questions_json", sa.Text(), nullable=False),
        sa.Column("scales_json", sa.Text(), nullable=False),
        sa.Column("total_items", sa.Integer(), nullable=False),
        sa.Column("estimated_time_minutes", sa.Integer(), nullable=False),
        sa.Column("raw_output", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("paradigm", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["survey_projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_questionnaires_project_id", "questionnaires", ["project_id"], unique=False)

    op.create_table(
        "questionnaire_responses",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("questionnaire_id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=True),
        sa.Column("respondent_label", sa.String(length=100), nullable=False),
        sa.Column("respondent_metadata_json", sa.Text(), nullable=True),
        sa.Column("answers_json", sa.Text(), nullable=False),
        sa.Column("completed", sa.Boolean(), nullable=False),
        sa.Column("interview_duration_s", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["questionnaire_id"], ["questionnaires.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["survey_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_questionnaire_responses_questionnaire_id",
        "questionnaire_responses",
        ["questionnaire_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_questionnaire_responses_questionnaire_id", table_name="questionnaire_responses")
    op.drop_table("questionnaire_responses")
    op.drop_index("ix_questionnaires_project_id", table_name="questionnaires")
    op.drop_table("questionnaires")
