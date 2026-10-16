"""
M.4 models: ReferenceCard (deployment-supplied reference knowledge), SkillsCluster, TriggerKeyword.
ReferenceCard uses table "reference_cards" to avoid conflict with survey.KnowledgeCard.
"""
from sqlalchemy import Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Integer, String, Text, Float, JSON
from app.models.base import Base, TimestampMixin


class ReferenceCard(Base, TimestampMixin):
    """Structured reference knowledge supplied by the deployment owner."""
    __tablename__ = "reference_cards"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_slug: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    source_file: Mapped[str] = mapped_column(String(500), nullable=False)
    source_section: Mapped[str] = mapped_column(String(100), nullable=True)
    keywords: Mapped[list] = mapped_column(JSON, default=list)
    core_concepts: Mapped[list] = mapped_column(JSON, default=list)
    practical_guidelines: Mapped[list] = mapped_column(JSON, default=list)
    case_studies: Mapped[list] = mapped_column(JSON, default=list)
    ethical_notes: Mapped[list] = mapped_column(JSON, default=list)
    cultural_knowledge: Mapped[list] = mapped_column(JSON, default=list)
    applicable_scenarios: Mapped[list] = mapped_column(JSON, default=list)
    confidence: Mapped[int] = mapped_column(Integer, default=3)
    extracted_at: Mapped[str] = mapped_column(String(50), nullable=True)
    language: Mapped[str | None] = mapped_column(String(12), nullable=True)
    field_context: Mapped[list | None] = mapped_column(JSON, nullable=True)
    method_tags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    material_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    clusters: Mapped[str] = mapped_column(String(200), default="")
    search_text: Mapped[str] = mapped_column(Text, default="")
    __table_args__ = (Index("ix_ref_slug", "source_slug"),)


class SkillsCluster(Base, TimestampMixin):
    """Skills cluster per M.3 design (P0-2 Cultural, P0-3 Methods, P0-4 Coding)."""
    __tablename__ = "skills_clusters"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cluster_id: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    sub_modules: Mapped[list] = mapped_column(JSON, default=list)
    prompt_template: Mapped[str] = mapped_column(Text, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=0)


class TriggerKeyword(Base, TimestampMixin):
    """Keyword -> cluster mapping for ContextualReminders."""
    __tablename__ = "trigger_keywords"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    keyword: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    cluster_id: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    sub_module_id: Mapped[str] = mapped_column(String(20), nullable=True)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    __table_args__ = (Index("ix_trigger_kw", "keyword", "cluster_id"),)
