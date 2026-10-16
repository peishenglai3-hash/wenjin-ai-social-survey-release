"""Survey platform data models — UserProfile, Project, Session, Analysis, Export."""

from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import UserAccount


class UserProfile(Base, TimestampMixin):
    __tablename__ = "user_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # ── Link to auth account (1:1) ──
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("user_accounts.id"), nullable=True, unique=True, index=True
    )
    user: Mapped[Optional["UserAccount"]] = relationship(back_populates="profile")
    mode: Mapped[str] = mapped_column(String(20), default="personal")  # personal / team
    gender: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    role: Mapped[str] = mapped_column(String(30), default="undergraduate")
    experience_level: Mapped[str] = mapped_column(String(30), default="beginner")
    age_range: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    mbti: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    paradigm_preference: Mapped[str] = mapped_column(String(30), default="qualitative")
    scenario_preference: Mapped[str] = mapped_column(String(30), default="community_interview")
    theme_preference: Mapped[str] = mapped_column(String(20), default="academic")  # academic / government / youth

    # ── Spectrum dimensions (L1 pseudo-continuous, 1–5 Likert scale) ──
    theory_driven: Mapped[int] = mapped_column(Integer, default=3)       # 1=理论驱动 ←→ 5=经验驱动
    methodological_rigidity: Mapped[int] = mapped_column(Integer, default=3)  # 1=严谨规范 ←→ 5=灵活探索
    analysis_depth: Mapped[int] = mapped_column(Integer, default=3)      # 1=广度优先 ←→ 5=深度优先
    structure_preference: Mapped[int] = mapped_column(Integer, default=3)    # 1=结构化 ←→ 5=开放式
    participation_level: Mapped[int] = mapped_column(Integer, default=3)     # 1=旁观观察 ←→ 5=深度参与
    tech_dependency: Mapped[int] = mapped_column(Integer, default=3)         # 1=低技术 ←→ 5=高技术
    writing_style: Mapped[int] = mapped_column(Integer, default=3)           # 1=学术正式 ←→ 5=通俗亲和
    learning_preference: Mapped[int] = mapped_column(Integer, default=3)     # 1=示范引导 ←→ 5=自主探索

    # ── User-facing settings (AI behaviour, UI, defaults, privacy) ──
    ai_temperature: Mapped[float] = mapped_column(default=0.5)               # 0.3–0.8
    ai_model_pref: Mapped[str] = mapped_column(String(10), default="auto")   # auto / flash / pro
    ai_hint_frequency: Mapped[str] = mapped_column(String(10), default="standard")  # off / low / standard / high
    ui_font_size: Mapped[str] = mapped_column(String(10), default="medium")  # small / medium / large
    ui_high_contrast: Mapped[bool] = mapped_column(default=False)
    default_export_format: Mapped[str] = mapped_column(String(30), default="report")
    auto_save_interval: Mapped[str] = mapped_column(String(10), default="60s")  # 30s / 60s / 300s / off

    projects: Mapped[list["SurveyProject"]] = relationship(back_populates="profile", cascade="all, delete-orphan")


class SurveyProject(Base, TimestampMixin):
    __tablename__ = "survey_projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(Integer, ForeignKey("user_profiles.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), default="未命名项目")
    research_direction: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    paradigm: Mapped[str] = mapped_column(String(30), default="qualitative")
    phase: Mapped[str] = mapped_column(String(30), default="pre_survey")  # pre_survey / during_survey / post_survey / completed
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft / active / completed
    topic_argumentation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    questionnaire_design: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    methodology_guidance: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    profile: Mapped["UserProfile"] = relationship(back_populates="projects")
    sessions: Mapped[list["SurveySession"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    analyses: Mapped[list["AnalysisResult"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    exports: Mapped[list["ExportDocument"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class ResearchInterestProfile(Base, TimestampMixin):
    """Cross-project research interest profile — accumulates insight across projects.

    Updated after each topic-argumentation session.  Tracks user's evolving
    discipline, topic, methodology, and theory preferences to enable
    increasingly personalized guidance over time (the "personalised memory"
    competitive barrier).
    """
    __tablename__ = "research_interests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user_profiles.id"), nullable=False, unique=True, index=True,
    )

    # ── Interest tags extracted across projects (stored as JSON arrays) ──
    discipline_tags_json: Mapped[str] = mapped_column(String(500), default="[]")
    # ["社会学", "政治学", "公共管理"]

    topic_keywords_json: Mapped[str] = mapped_column(String(1000), default="[]")
    # ["基层治理", "干部晋升", "农村土地流转"]

    methodology_history_json: Mapped[str] = mapped_column(String(500), default="[]")
    # ["深度访谈", "参与观察", "问卷调查"]

    theory_preferences_json: Mapped[str] = mapped_column(String(500), default="[]")
    # ["场域理论", "差序格局", "制度分析"]

    # ── Inferred academic stage & scope ──
    inferred_academic_stage: Mapped[str] = mapped_column(
        String(30), default="proposal",
    )  # proposal / fieldwork / writing / defense

    preferred_research_scope: Mapped[str] = mapped_column(
        String(20), default="meso",
    )  # micro / meso / macro

    # ── Behavioural metrics ──
    previous_projects_count: Mapped[int] = mapped_column(Integer, default=0)
    completed_projects_count: Mapped[int] = mapped_column(Integer, default=0)
    topic_refinement_iterations: Mapped[int] = mapped_column(Integer, default=1)
    citation_comfort_level: Mapped[int] = mapped_column(Integer, default=3)  # 1-5

    # ── Most recent activity ──
    last_topic: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    last_paradigm: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    last_project_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("survey_projects.id"), nullable=True,
    )


class SurveySession(Base, TimestampMixin):
    __tablename__ = "survey_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("survey_projects.id"), nullable=False)
    transcript_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    summary_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    hints_generated: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    project: Mapped["SurveyProject"] = relationship(back_populates="sessions")


class AnalysisResult(Base, TimestampMixin):
    __tablename__ = "analysis_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("survey_projects.id"), nullable=False)
    analysis_type: Mapped[str] = mapped_column(String(30), default="thematic")
    content: Mapped[str] = mapped_column(Text, default="")

    project: Mapped["SurveyProject"] = relationship(back_populates="analyses")


class ExportDocument(Base, TimestampMixin):
    __tablename__ = "export_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("survey_projects.id"), nullable=False)
    format_type: Mapped[str] = mapped_column(String(30), default="report")
    content: Mapped[str] = mapped_column(Text, default="")

    project: Mapped["SurveyProject"] = relationship(back_populates="exports")


class ScenarioDesign(Base, TimestampMixin):
    """User-designed survey scenario — scene workshop output."""
    __tablename__ = "scenario_designs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(Integer, ForeignKey("user_profiles.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), default="未命名场景")
    scenario_type: Mapped[str] = mapped_column(String(50), default="custom")
    description: Mapped[str] = mapped_column(Text, default="")
    location_context: Mapped[str] = mapped_column(Text, default="")
    method_recommendations: Mapped[str] = mapped_column(Text, default="")
    pitfalls: Mapped[str] = mapped_column(Text, default="")
    ethical_notes: Mapped[str] = mapped_column(Text, default="")
    tool_recommendations: Mapped[str] = mapped_column(Text, default="")
    interview_guide: Mapped[str] = mapped_column(Text, default="")
    full_output: Mapped[str] = mapped_column(Text, default="")


class KnowledgeCard(Base, TimestampMixin):
    """Distilled methodology insight — extracted from project experience, reusable across projects."""
    __tablename__ = "knowledge_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(Integer, ForeignKey("user_profiles.id"), nullable=False)
    source_project_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("survey_projects.id"), nullable=True)
    category: Mapped[str] = mapped_column(String(30), default="methodology")  # methodology | pitfall | tool | ethics | theory | workflow
    title: Mapped[str] = mapped_column(String(200), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[str] = mapped_column(String(500), default="[]")  # JSON array of tag strings
    paradigm: Mapped[str] = mapped_column(String(30), default="qualitative")
    phase: Mapped[str] = mapped_column(String(30), default="pre_survey")
    theme: Mapped[str] = mapped_column(String(20), default="academic")
    reuse_count: Mapped[int] = mapped_column(Integer, default=0)
    importance: Mapped[int] = mapped_column(Integer, default=3)  # 1-5 AI-assessed importance


class UserMemory(Base, TimestampMixin):
    """Hermes-style persistent user memory — extracted from dialogue, injected into future context.

    Each row is one atomic memory fragment. category + key form a natural compound key
    within a profile so the same insight isn't stored twice (upsert on conflict).
    """
    __tablename__ = "user_memories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(Integer, ForeignKey("user_profiles.id"), nullable=False)

    category: Mapped[str] = mapped_column(String(40), default="preference")
    # preference | interest | expertise | habit | goal | constraint | methodology | tool | pitfall | note

    key: Mapped[str] = mapped_column(String(200), default="")
    # Short stable label, e.g. "favoured_paradigm", "common_mistake_sampling", "hates_jargon"

    value: Mapped[str] = mapped_column(Text, default="")
    # The actual memory content — a sentence or short paragraph

    confidence: Mapped[float] = mapped_column(default=0.5)  # 0.0–1.0 AI confidence
    source: Mapped[str] = mapped_column(String(30), default="dialogue")  # dialogue | explicit | inference | import
    importance: Mapped[int] = mapped_column(Integer, default=3)  # 1-5 AI-assessed importance
    hit_count: Mapped[int] = mapped_column(Integer, default=0)  # times injected into context
    last_hit_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # ── Denormalised for quick filtering ──
    paradigm: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    phase: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    tags: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # JSON array


class UserSkill(Base, TimestampMixin):
    """User-authored (or AI-extracted) reusable skill / prompt template.

    The simplest form is a saved prompt template; advanced forms add rule chains.
    Path 1 (Prompt Template) is the v0.4.0 MVP scope.
    """
    __tablename__ = "user_skills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(Integer, ForeignKey("user_profiles.id"), nullable=False)

    name: Mapped[str] = mapped_column(String(200), default="未命名技能")
    description: Mapped[str] = mapped_column(Text, default="")
    prompt_template: Mapped[str] = mapped_column(Text, default="")
    # The saved system/user prompt; {context} placeholders are filled at invocation time

    skill_type: Mapped[str] = mapped_column(String(30), default="prompt_template")
    # prompt_template | rule_chain | custom_workflow

    category: Mapped[str] = mapped_column(String(30), default="general")
    # questionnaire | interview | analysis | writing | methodology | general

    tags: Mapped[str] = mapped_column(String(500), default="[]")  # JSON array
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    is_public: Mapped[bool] = mapped_column(default=False)  # shared to skill marketplace
    source_dialogue_snippet: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # The original Q&A that inspired this skill (for context)

    # Marketplace metadata used by the existing community router. These fields
    # are additive and do not change private skill behavior.
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    published_version: Mapped[str] = mapped_column(String(30), default="1.0.0")
    fork_count: Mapped[int] = mapped_column(Integer, default=0)
    rating_avg: Mapped[float] = mapped_column(Float, default=0.0)
    rating_count: Mapped[int] = mapped_column(Integer, default=0)
    download_count: Mapped[int] = mapped_column(Integer, default=0)
    readme: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    example_input: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    example_output: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    compatible_models: Mapped[str] = mapped_column(String(1000), default="[]")
    min_app_version: Mapped[str] = mapped_column(String(30), default="0.2.0")
    forked_from_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    fork_lineage: Mapped[str] = mapped_column(String(2000), default="[]")


class ReflectionSession(Base, TimestampMixin):
    """A structured sociological reflexivity dialogue — 反思性会话.

    Triggered after key milestones (fieldwork completed, analysis completed,
    project completed).  Each session contains a series of Q&A rounds where
    the AI guides the user through reflection questions grounded in French
    Pragmatism, Ethnomethodology, and Bourdieu's reflexive sociology.

    The extracted insights feed into the profile iteration pipeline
    (ProfileIterator) which gradually adjusts the user's spectrum dimensions.
    """
    __tablename__ = "reflection_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(Integer, ForeignKey("user_profiles.id"), nullable=False)

    trigger_type: Mapped[str] = mapped_column(String(40), default="fieldwork_completed")
    # fieldwork_completed | analysis_completed | project_completed

    source_session_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # FK to survey_sessions.id if triggered by a fieldwork session

    source_project_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("survey_projects.id"), nullable=True)
    # FK to survey_projects.id if triggered in project context

    status: Mapped[str] = mapped_column(String(20), default="in_progress")
    # in_progress | completed | abandoned

    # ── Dialogue content stored as JSON arrays ──
    questions_json: Mapped[str] = mapped_column(Text, default="[]")
    # JSON array of question dicts: [{id, prompt, tradition, spectrum_touch}]

    answers_json: Mapped[str] = mapped_column(Text, default="[]")
    # JSON array of answer dicts: [{question_id, user_answer, ai_followup}]

    # ── AI-generated outputs ──
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Human-readable reflection summary (200-300 chars)

    insights_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # JSON array of extracted insights: [{dimension, direction, confidence, rationale}]

    spectrum_shifts_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # JSON array of recommended spectrum adjustments


class IterationInsight(Base, TimestampMixin):
    """A single profile evolution insight — 迭代洞察.

    Each row records one meaningful shift in the user's methodological spectrum
    (or other profile dimension), discovered through reflection sessions.
    Over time, these form a traceable evolution history of the user's
    development as a researcher.

    Used by the ProfileIterator to compute cumulative adjustment recommendations
    while preventing profile "drift" (over-rapid changes from noisy insights).
    """
    __tablename__ = "iteration_insights"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(Integer, ForeignKey("user_profiles.id"), nullable=False)

    source_reflection_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("reflection_sessions.id"), nullable=True,
    )
    source_project_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("survey_projects.id"), nullable=True,
    )

    dimension: Mapped[str] = mapped_column(String(40), default="theory_driven")
    # Which spectrum/profile dimension this insight affects

    direction: Mapped[int] = mapped_column(Integer, default=0)
    # -2 to +2: direction and strength of recommended shift

    confidence: Mapped[float] = mapped_column(default=0.5)
    # AI's confidence in this insight (0.0-1.0)

    rationale: Mapped[str] = mapped_column(Text, default="")
    # Why this shift is recommended

    evidence: Mapped[str] = mapped_column(Text, default="")
    # Quote or paraphrase from the user's reflection supporting this insight

    is_applied: Mapped[bool] = mapped_column(default=False)
    # Whether this insight has been applied to the user's profile

    applied_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    previous_value: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # The spectrum value before this insight was applied
    new_value: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # The spectrum value after this insight was applied


class FieldNote(Base, TimestampMixin):
    """AI-generated or manual field note attached to a survey session.

    Four types mirror standard qualitative fieldwork documentation:
      - quote:        key verbatim quote with estimated timestamp
      - observation:  environmental/situational observation inferred from dialogue
      - reflection:   methodological reflection on interview quality
      - memo:         analytic memo (preliminary theoretical connections, hypotheses)
    """
    __tablename__ = "field_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("survey_sessions.id"), nullable=False, index=True
    )
    project_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("survey_projects.id"), nullable=True
    )

    note_type: Mapped[str] = mapped_column(
        String(20), default="memo"
    )  # "quote" | "observation" | "reflection" | "memo" | "methodology"

    content: Mapped[str] = mapped_column(Text, default="")

    timestamp_in_recording: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Seconds from recording start (estimated for AI-generated notes)

    tags: Mapped[str] = mapped_column(String(500), default="[]")
    # JSON array of tag strings, e.g. '["key moment","follow-up needed"]'

    ai_generated: Mapped[bool] = mapped_column(Boolean, default=True)
    # Whether this note was auto-generated by AI

    ai_edited: Mapped[bool] = mapped_column(Boolean, default=False)
    # Whether a human has manually edited this note after AI generation

    editor_profile_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user_profiles.id"), nullable=True
    )

    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class CodebookCode(Base, TimestampMixin):
    """A single code in a project's qualitative coding codebook.

    Supports hierarchical coding (parent_code_id) and four coding paradigms:
    grounded_theory, thematic_analysis, content_analysis, framework_analysis.
    """
    __tablename__ = "codebook_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("survey_projects.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), default="")
    definition: Mapped[str] = mapped_column(Text, default="")
    example: Mapped[str] = mapped_column(Text, default="")
    exclusion_criteria: Mapped[str] = mapped_column(Text, default="")
    parent_code_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("codebook_codes.id"), nullable=True
    )
    color: Mapped[str] = mapped_column(String(7), default="#3B82F6")
    paradigm: Mapped[str] = mapped_column(
        String(30), default="thematic_analysis"
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by_profile_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user_profiles.id"), nullable=True
    )


class CodingAssignment(Base, TimestampMixin):
    """Links a code to a specific span of text in a survey session transcript.

    Each assignment records: which code, which session, the exact text span
    (character offsets), the quoted text, who coded it, and AI confidence.
    """
    __tablename__ = "coding_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("codebook_codes.id"), nullable=False, index=True
    )
    session_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("survey_sessions.id"), nullable=False, index=True
    )
    span_start: Mapped[int] = mapped_column(Integer, default=0)
    span_end: Mapped[int] = mapped_column(Integer, default=0)
    quote_text: Mapped[str] = mapped_column(Text, default="")
    coder_profile_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user_profiles.id"), nullable=True
    )
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    is_ai_suggested: Mapped[bool] = mapped_column(Boolean, default=False)


class CodebookVersion(Base, TimestampMixin):
    """A snapshot of the full codebook at a point in time (for audit trail).

    Stores the complete codebook as a JSON snapshot so researchers can
    trace how their coding framework evolved across versions.
    """
    __tablename__ = "codebook_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("survey_projects.id"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, default=1)
    snapshot_json: Mapped[str] = mapped_column(Text, default="{}")
    created_by_profile_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user_profiles.id"), nullable=True
    )
    changelog: Mapped[str] = mapped_column(Text, default="")


class Questionnaire(Base, TimestampMixin):
    """Structured questionnaire — parsed from AI-generated JSON in QuestionnaireDesign."""
    __tablename__ = "questionnaires"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("survey_projects.id"), nullable=False, index=True,
    )
    title: Mapped[str] = mapped_column(String(300), default="未命名问卷")
    constructs_json: Mapped[str] = mapped_column(Text, default="[]")
    questions_json: Mapped[str] = mapped_column(Text, default="[]")
    scales_json: Mapped[str] = mapped_column(Text, default="[]")
    total_items: Mapped[int] = mapped_column(Integer, default=0)
    estimated_time_minutes: Mapped[int] = mapped_column(Integer, default=0)
    raw_output: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    paradigm: Mapped[str] = mapped_column(String(30), default="quantitative")

    responses: Mapped[list["QuestionnaireResponse"]] = relationship(
        back_populates="questionnaire", cascade="all, delete-orphan",
    )


class QuestionnaireResponse(Base, TimestampMixin):
    """One complete response to a questionnaire (one respondent)."""
    __tablename__ = "questionnaire_responses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    questionnaire_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("questionnaires.id"), nullable=False, index=True,
    )
    session_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("survey_sessions.id"), nullable=True,
    )
    respondent_label: Mapped[str] = mapped_column(String(100), default="")
    respondent_metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    answers_json: Mapped[str] = mapped_column(Text, default="{}")
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    interview_duration_s: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    questionnaire: Mapped["Questionnaire"] = relationship(back_populates="responses")
