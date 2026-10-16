"""Topic design, questionnaire, and survey project CRUD — Pre-Survey phase."""

import json
import logging
import re

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps_auth import get_current_profile
from app.api.deps import get_ai_service, get_db
from app.models.collaboration import ProjectMember
from app.models.survey import SurveyProject, UserProfile
from app.services.ai import AIService
from app.skills.mode_prompts import get_mode_modifier, get_distilled_task_prompt, get_mode_task_config

logger = logging.getLogger(__name__)

# ── Streaming HTML filter ───────────────────────────────────────────────
# Catches HTML tags that appear as complete tokens in SSE streams.
# Aggressive patterns because LLMs (especially DeepSeek) occasionally emit
# raw HTML mixed with Markdown in streaming mode.

_STREAM_HTML_RE = re.compile(
    r"</?\s*(br|p|div|span|html|body|head|li|ul|ol|table|tr|td|th|h[1-6]|a|img|input|hr)\s*/?>",
    re.IGNORECASE,
)
_STREAM_ENTITY_RE = re.compile(r"&(nbsp|lt|gt|amp|quot|apos);")


def _strip_stream_token(token: str) -> str:
    """Remove HTML tags/entities from a single streaming token."""
    token = _STREAM_HTML_RE.sub("", token)
    token = _STREAM_ENTITY_RE.sub("", token)
    # Collapse orphan angle brackets (partial tags from token boundaries)
    token = token.replace("<>", "").replace("</>", "")
    return token

logger = logging.getLogger(__name__)

router = APIRouter(tags=["pre-survey"])

BASE_TOPIC_SYSTEM = (
    "你是一位资深的社会科学研究方法专家。"
    "你的任务是根据用户的研究方向，提供选题论证、方法论建议和研究设计优化。"
)


def _build_topic_system_prompt(theme: str = "academic") -> str:
    """Build a mode-aware topic design system prompt."""
    parts = [BASE_TOPIC_SYSTEM]
    mode_mod = get_mode_modifier(theme, "system")
    if mode_mod:
        parts.append(mode_mod)
    topic_mod = get_mode_modifier(theme, "topic")
    if topic_mod:
        parts.append(topic_mod)
    distilled = get_distilled_task_prompt(theme, "topic")
    if distilled:
        parts.append(distilled)
    parts.append(
        "请针对用户输入，从以下维度给出具体建议：\n"
        "1. 选题聚焦（如何缩小/细化研究问题）\n"
        "2. 理论框架推荐（适合的社会学/心理学/传播学理论）\n"
        "3. 研究方法匹配（质性/量化/混合方法的适用性分析）\n"
        "4. 抽样策略（样本量估计、抽样方法建议）\n"
        "5. 潜在的研究局限与应对\n"
        "6. 后续步骤建议\n"
        "用中文输出，Markdown格式，每条建议要有具体可操作的指导。"
    )
    return "\n\n".join(parts)


@router.post("/topic/assist")
async def topic_assist_post(payload: dict, ai: AIService = Depends(get_ai_service)):
    """AI-assisted topic design with mode-specific structured suggestions."""
    query = payload.get("query", "")
    paradigm = payload.get("paradigm", "qualitative")
    theme = payload.get("theme", "academic")

    if not query.strip():
        return {"error": "query is required"}

    if theme not in ("academic", "government", "youth"):
        theme = "academic"

    system_prompt = _build_topic_system_prompt(theme)
    task_cfg = get_mode_task_config(theme, "topic")
    user_message = f"研究方向: {query}\n研究范式偏好: {paradigm}"
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    result = await ai.chat(messages, temperature=task_cfg["temperature"], max_tokens=task_cfg["max_tokens"], task="topic")
    return {"query": query, "paradigm": paradigm, "theme": theme, "suggestions": result}


@router.post("/topic/assist/stream")
async def topic_assist_stream(payload: dict, ai: AIService = Depends(get_ai_service)):
    """AI-assisted topic design with mode-specific streaming SSE response."""
    query = payload.get("query", "")
    paradigm = payload.get("paradigm", "qualitative")
    theme = payload.get("theme", "academic")

    if not query.strip():
        return {"error": "query is required"}

    if theme not in ("academic", "government", "youth"):
        theme = "academic"

    system_prompt = _build_topic_system_prompt(theme)
    task_cfg = get_mode_task_config(theme, "topic")
    user_message = f"研究方向: {query}\n研究范式偏好: {paradigm}"
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    async def event_stream():
        async for token in ai.chat_stream(messages, temperature=task_cfg["temperature"], max_tokens=task_cfg["max_tokens"], task="topic"):
            yield f"data: {json.dumps({'token': token})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/topic/assist/enhanced")
async def topic_assist_enhanced(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    ai: AIService = Depends(get_ai_service),
):
    """Enhanced topic design with user profile + literature + M.4 knowledge cards.

    Accepts:
      - query: research direction (required)
      - profile_id: user profile ID for personalization (optional, default 1)
      - paradigm: qualitative / quantitative / mixed
      - include_literature: whether to search literature (default True)
      - include_reminders: whether to inject M.4 knowledge cards (default True)

    Returns SSE stream of the enhanced argumentation report with citations.
    """
    query = payload.get("query", "")
    profile_id = payload.get("profile_id", 1)
    paradigm = payload.get("paradigm", "qualitative")
    theme = payload.get("theme", "academic")
    include_literature = payload.get("include_literature", True)
    include_reminders = payload.get("include_reminders", True)

    if not query.strip():
        return {"error": "query is required"}

    # 1. Read user profile for personalization
    profile = None
    try:
        result = await db.execute(
            select(UserProfile).where(UserProfile.id == profile_id)
        )
        profile = result.scalar_one_or_none()
    except Exception:
        logger.warning("Profile lookup failed for id=%s", profile_id)

    # 2. Build personalized system prompt
    parts = [_build_topic_system_prompt(theme)]

    if profile:
        profile_ctx = _build_profile_context(profile)
        parts.insert(0, profile_ctx)

    # 3. Inject literature context
    if include_literature:
        try:
            from app.services.literature_service import get_literature_service
            lit_service = get_literature_service()
            papers = await lit_service.search(query, top_n=10)
            if papers:
                lit_ctx = _build_literature_context(papers)
                parts.append(lit_ctx)
                logger.info("Injected %d literature results for topic", len(papers))
        except Exception as e:
            logger.warning("Literature injection failed (non-fatal): %s", e)

    # 4. Inject M.4 knowledge card reminders
    if include_reminders:
        try:
            from app.services.contextual_reminders import get_reminders
            reminders = await get_reminders(db, context_text=query, top_n=5)
            if reminders:
                reminder_ctx = _build_reminder_context(reminders)
                parts.append(reminder_ctx)
                logger.info("Injected %d knowledge card reminders", len(reminders))
        except Exception as e:
            logger.warning("Reminder injection failed (non-fatal): %s", e)

    system_prompt = "\n\n".join(parts)

    # 5. Build user message
    task_cfg = get_mode_task_config(theme, "topic")
    user_message = f"研究方向: {query}\n研究范式偏好: {paradigm}"
    if profile:
        user_message += (
            f"\n用户背景: {profile.role} ({profile.experience_level}), "
            f"范式偏好: {profile.paradigm_preference}"
        )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    async def event_stream():
        async for token in ai.chat_stream(
            messages, temperature=task_cfg["temperature"],
            max_tokens=task_cfg["max_tokens"], task="topic",
        ):
            yield f"data: {json.dumps({'token': token})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _build_profile_context(profile: UserProfile) -> str:
    """Render user profile as a personalized instruction block."""
    labels = {
        "theory_driven": {1: "偏实践经验", 3: "理论与经验并重", 5: "偏理论建构"},
        "methodological_rigidity": {1: "偏好严谨规范方法", 3: "灵活与规范兼顾", 5: "偏好灵活探索"},
        "analysis_depth": {1: "偏好多案例比较", 3: "深度与广度兼顾", 5: "偏好单案例深描"},
        "writing_style": {1: "学术正式风格", 3: "平衡风格", 5: "通俗易懂风格"},
        "learning_preference": {1: "需要明确示范引导", 3: "自主与引导兼顾", 5: "偏好自主探索"},
    }

    lines = ["## 用户画像（个性化调整依据）"]
    lines.append(f"- 学术身份: {profile.role} ({profile.experience_level})")
    lines.append(f"- 研究范式偏好: {profile.paradigm_preference}")
    lines.append(f"- 场景偏好: {profile.scenario_preference}")

    for dim, label_map in labels.items():
        val = getattr(profile, dim, 3)
        label = label_map.get(val, label_map[3])
        lines.append(f"- {dim}: {label}")

    lines.append(
        "\n请根据以上画像调整论证的深度、广度、方法论建议和语言风格。"
        "初级研究者多给具体示例和操作指导；高级研究者多给理论深度和批判性讨论。"
    )
    return "\n".join(lines)


def _build_literature_context(papers) -> str:
    """Build a literature review context block for the system prompt."""
    lines = ["## 相关学术文献（引用时请标注 [文献N]）", ""]
    for i, p in enumerate(papers[:10], 1):
        authors = ", ".join(p.authors[:3])
        if len(p.authors) > 3:
            authors += " et al."
        year_str = f" ({p.year})" if p.year else ""
        lines.append(
            f"[文献{i}] {p.title}{year_str} — {authors}"
        )
        if p.abstract:
            lines.append(f"  摘要: {p.abstract[:300]}")
        if p.doi:
            lines.append(f"  DOI: {p.doi}")
        lines.append("")
    lines.append("请在选题论证的相关维度中引用以上文献，确保学术依据充分。")
    return "\n".join(lines)


def _build_reminder_context(reminders: list[dict]) -> str:
    """Build a knowledge card insight block for the system prompt."""
    lines = ["## 方法论知识库提醒（来自学术参考文献卡片）", ""]
    for i, r in enumerate(reminders[:5], 1):
        lines.append(f"### 知识卡片 {i}: {r.get('cluster_name', '')}")
        lines.append(f"{r.get('reminder_text', '')}")
        lines.append(f"来源: {r.get('source_slug', '')} (置信度: {r.get('confidence', 3)})")
        lines.append("")
    return "\n".join(lines)


@router.post("/topic/questionnaire")
async def topic_questionnaire(payload: dict, ai: AIService = Depends(get_ai_service)):
    """Generate a structured questionnaire based on research topic."""
    from app.skills.registry import skill_registry
    from app.skills.questionnaire import QuestionnaireSkill

    skill = skill_registry.get("questionnaire")
    if not skill:
        return {"error": "Questionnaire skill not registered"}

    user_input = {
        "research_topic": payload.get("research_topic", ""),
        "target_population": payload.get("target_population", ""),
        "research_paradigm": payload.get("paradigm", "quantitative"),
    }
    if not user_input["research_topic"].strip():
        return {"error": "research_topic is required"}

    result = await skill.execute(ai, user_input)
    return {"questionnaire": result.content}


@router.post("/topic/questionnaire/stream")
async def topic_questionnaire_stream(payload: dict, ai: AIService = Depends(get_ai_service)):
    """Generate a structured questionnaire with SSE streaming response.

    Supports step-by-step generation via the `step` parameter:
    - full: complete questionnaire (all 7 sections + JSON)
    - concepts: only construct/concept framework
    - scales: only scale recommendations
    - questions: only question items + JSON
    - review: methodology review only
    """
    from app.skills.registry import skill_registry
    from app.skills.questionnaire import QuestionnaireSkill

    skill = skill_registry.get("questionnaire")
    if not skill:
        return {"error": "Questionnaire skill not registered"}

    topic = payload.get("research_topic", "")
    population = payload.get("target_population", "")
    experience_level = payload.get("experience_level", "beginner")
    paradigm = payload.get("paradigm", "quantitative")
    existing_scales = payload.get("existing_scales", "")
    step = payload.get("step", "full")

    if not topic.strip():
        return {"error": "research_topic is required"}

    skill_instance = QuestionnaireSkill()
    system_msg = skill_instance.system_prompt(None, experience_level)

    step_instructions = {
        "full": "请按照系统提示的完整框架，输出包含所有7个部分的问卷设计方案。",
        "concepts": "请仅输出「核心构念与概念框架」部分。深入分析每个构念的理论来源、操作化路径和测量维度。",
        "scales": "请仅输出「推荐量表」部分。为每个构念提供2-3个候选量表，对比信效度和文化适用性。",
        "questions": "请仅输出「完整问卷题项」和「结构化JSON」部分。生成立即可用的完整问卷。",
        "review": "请以方法论审阅模式，仅输出「信效度保障策略」和「实施注意事项」部分。",
    }

    instruction = step_instructions.get(step, step_instructions["full"])

    user_msg = (
        f"研究主题：{topic}\n"
        f"目标人群：{population or '未指定'}\n"
        f"研究范式：{paradigm}\n"
        + (f"已知相关量表：{existing_scales}\n" if existing_scales else "")
        + f"\n{instruction}"
    )

    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]

    max_tok = 8192 if step == "full" else 4096

    async def event_stream():
        async for token in ai.chat_stream(messages, temperature=0.7, max_tokens=max_tok, task="questionnaire"):
            clean = _strip_stream_token(token)
            if clean:
                yield f"data: {json.dumps({'token': clean})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/topic/questionnaire/download")
async def topic_questionnaire_download(payload: dict):
    """Generate a downloadable .docx or .md file from questionnaire content.
    Does NOT call AI — purely converts the provided Markdown content to the requested format.
    """
    from urllib.parse import quote
    from app.services.export_service import generate_docx

    content = payload.get("content", "")
    file_type = payload.get("file_type", "docx")
    title = payload.get("title", "问卷设计")

    if not content.strip():
        return {"error": "content is required"}

    safe_title = title.replace('"', '').replace('\n', ' ').strip() or "问卷设计"

    if file_type == "docx":
        docx_bytes = generate_docx(content, safe_title)
        encoded_filename = quote(f"{safe_title}.docx")
        return Response(
            content=docx_bytes,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
                "Content-Length": str(len(docx_bytes)),
            },
        )
    else:
        encoded = content.encode("utf-8")
        encoded_filename = quote(f"{safe_title}.md")
        return Response(
            content=encoded,
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
                "Content-Length": str(len(encoded)),
            },
        )


# ── Project CRUD ─────────────────────────────────────────────────

@router.post("/projects")
async def create_project(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    profile: UserProfile = Depends(get_current_profile),
):
    project = SurveyProject(
        profile_id=profile.id,
        title=payload.get("title", "未命名项目"),
        research_direction=payload.get("research_direction", ""),
        paradigm=payload.get("paradigm", "qualitative"),
        phase="pre_survey",
        status="draft",
    )
    db.add(project)
    await db.flush()
    # New projects carry an explicit owner row; the migration/helper backfills
    # the same invariant for projects created before collaboration V1.
    db.add(ProjectMember(project_id=project.id, profile_id=profile.id, role="owner", status="active"))
    await db.commit()
    await db.refresh(project)
    return {
        "id": project.id,
        "title": project.title,
        "research_direction": project.research_direction,
        "paradigm": project.paradigm,
        "phase": project.phase,
        "status": project.status,
        "created_at": str(project.created_at) if project.created_at else None,
    }


@router.get("/projects")
async def list_projects(
    db: AsyncSession = Depends(get_db),
    profile: UserProfile = Depends(get_current_profile),
):
    result = await db.execute(
        select(SurveyProject)
        .where(SurveyProject.profile_id == profile.id)
        .order_by(SurveyProject.created_at.desc())
    )
    projects = result.scalars().all()
    return {
        "projects": [
            {
                "id": p.id,
                "title": p.title,
                "research_direction": p.research_direction,
                "paradigm": p.paradigm,
                "phase": p.phase,
                "status": p.status,
                "created_at": str(p.created_at) if p.created_at else None,
            }
            for p in projects
        ]
    }


@router.get("/projects/{project_id}")
async def get_project(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    profile: UserProfile = Depends(get_current_profile),
):
    result = await db.execute(
        select(SurveyProject).where(
            SurveyProject.id == project_id,
            SurveyProject.profile_id == profile.id,
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        return {"error": "Project not found"}
    return {
        "id": project.id,
        "profile_id": project.profile_id,
        "title": project.title,
        "research_direction": project.research_direction,
        "paradigm": project.paradigm,
        "phase": project.phase,
        "status": project.status,
        "topic_argumentation": project.topic_argumentation,
        "questionnaire_design": project.questionnaire_design,
        "methodology_guidance": project.methodology_guidance,
        "created_at": str(project.created_at) if project.created_at else None,
        "updated_at": str(project.updated_at) if project.updated_at else None,
    }


@router.put("/projects/{project_id}")
async def update_project(
    project_id: int,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    profile: UserProfile = Depends(get_current_profile),
):
    result = await db.execute(
        select(SurveyProject).where(
            SurveyProject.id == project_id,
            SurveyProject.profile_id == profile.id,
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        return {"error": "Project not found"}

    updatable = ["title", "research_direction", "paradigm", "phase", "status",
                  "topic_argumentation", "questionnaire_design", "methodology_guidance"]
    for field in updatable:
        if field in payload:
            setattr(project, field, payload[field])

    await db.commit()
    await db.refresh(project)
    return {"id": project.id, "title": project.title, "phase": project.phase, "status": project.status}
