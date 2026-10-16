"""add deployment-owned knowledge card tables

Revision ID: 20261016_knowledge
Revises: 20261016_collaboration
Create Date: 2026-10-16
"""

from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa


revision: str = "20261016_knowledge"
down_revision: Union[str, Sequence[str], None] = "20261016_collaboration"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
    ]


def _table_exists(name: str) -> bool:
    # Offline SQL generation starts from the clean revision chain and cannot
    # inspect a MockConnection. Online upgrades retain the legacy-table guard.
    if context.is_offline_mode():
        return False
    return sa.inspect(op.get_bind()).has_table(name)


def _index_exists(table_name: str, index_name: str) -> bool:
    if context.is_offline_mode():
        return False
    return any(
        index.get("name") == index_name
        for index in sa.inspect(op.get_bind()).get_indexes(table_name)
    )


def upgrade() -> None:
    # These tables existed in some old AUTO_CREATE_SCHEMA deployments but did
    # not have an Alembic revision. Preserve such data while making clean
    # installs reproducible.
    if not _table_exists("reference_cards"):
        op.create_table(
            "reference_cards",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("source_slug", sa.String(length=200), nullable=False),
            sa.Column("source_file", sa.String(length=500), nullable=False),
            sa.Column("source_section", sa.String(length=100), nullable=True),
            sa.Column("keywords", sa.JSON(), nullable=False),
            sa.Column("core_concepts", sa.JSON(), nullable=False),
            sa.Column("practical_guidelines", sa.JSON(), nullable=False),
            sa.Column("case_studies", sa.JSON(), nullable=False),
            sa.Column("ethical_notes", sa.JSON(), nullable=False),
            sa.Column("cultural_knowledge", sa.JSON(), nullable=False),
            sa.Column("applicable_scenarios", sa.JSON(), nullable=False),
            sa.Column("confidence", sa.Integer(), nullable=False),
            sa.Column("extracted_at", sa.String(length=50), nullable=True),
            sa.Column("clusters", sa.String(length=200), nullable=False),
            sa.Column("search_text", sa.Text(), nullable=False),
            *_timestamps(),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _index_exists("reference_cards", "ix_ref_slug"):
        op.create_index("ix_ref_slug", "reference_cards", ["source_slug"])
    if not _index_exists("reference_cards", "ix_reference_cards_source_slug"):
        op.create_index("ix_reference_cards_source_slug", "reference_cards", ["source_slug"])

    if not _table_exists("skills_clusters"):
        op.create_table(
            "skills_clusters",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("cluster_id", sa.String(length=20), nullable=False),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("sub_modules", sa.JSON(), nullable=False),
            sa.Column("prompt_template", sa.Text(), nullable=True),
            sa.Column("priority", sa.Integer(), nullable=False),
            *_timestamps(),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _index_exists("skills_clusters", "ix_skills_clusters_cluster_id"):
        op.create_index("ix_skills_clusters_cluster_id", "skills_clusters", ["cluster_id"], unique=True)

    if not _table_exists("trigger_keywords"):
        op.create_table(
            "trigger_keywords",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("keyword", sa.String(length=100), nullable=False),
            sa.Column("cluster_id", sa.String(length=20), nullable=False),
            sa.Column("sub_module_id", sa.String(length=20), nullable=True),
            sa.Column("weight", sa.Float(), nullable=False),
            *_timestamps(),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _index_exists("trigger_keywords", "ix_trigger_keywords_keyword"):
        op.create_index("ix_trigger_keywords_keyword", "trigger_keywords", ["keyword"])
    if not _index_exists("trigger_keywords", "ix_trigger_keywords_cluster_id"):
        op.create_index("ix_trigger_keywords_cluster_id", "trigger_keywords", ["cluster_id"])
    if not _index_exists("trigger_keywords", "ix_trigger_kw"):
        op.create_index("ix_trigger_kw", "trigger_keywords", ["keyword", "cluster_id"])


def downgrade() -> None:
    op.drop_index("ix_trigger_kw", table_name="trigger_keywords")
    op.drop_index("ix_trigger_keywords_cluster_id", table_name="trigger_keywords")
    op.drop_index("ix_trigger_keywords_keyword", table_name="trigger_keywords")
    op.drop_table("trigger_keywords")
    op.drop_index("ix_skills_clusters_cluster_id", table_name="skills_clusters")
    op.drop_table("skills_clusters")
    op.drop_index("ix_reference_cards_source_slug", table_name="reference_cards")
    op.drop_index("ix_ref_slug", table_name="reference_cards")
    op.drop_table("reference_cards")
