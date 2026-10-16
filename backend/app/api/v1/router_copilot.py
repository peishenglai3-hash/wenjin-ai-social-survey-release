"""Survey Copilot — floating AI Q&A with full survey context injection.

Unlike fieldwork hints (AI pro-actively pushes suggestions based on transcript),
the Copilot lets users ask questions on their own initiative. It injects the
full survey context (profile, project, current phase, recent transcripts) into
the system prompt so answers are always contextualised.

Personalisation architecture (v2 — ClusterRouter):
  UserProfile → ClusterRouter.match(profile) → assembled prompt fragments
  Replaces the old monolithic theme_system + hardcoded label maps with
  composable, pre-compiled PromptFragments across 6 dimensions.
"""

import json
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_ai_service, get_db
from app.api.deps_auth import require_user, get_current_profile
from app.models.user import UserAccount
from app.services.ai import AIService
from app.models.survey import SurveyProject, SurveySession, UserProfile
from app.services.cluster_router import cluster_router
from app.services.memory_service import MemoryService
from app.services.wise_service import WISEService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/copilot", tags=["copilot"])

# ── Conversation history buffer (in-memory, per-user for now) ────────
conversation_history: dict[int, list[dict]] = {}
MAX_HISTORY = 10  # keep last 10 messages (5 rounds)


async def _owned_project(
    db: AsyncSession,
    project_id: object,
    profile_id: int,
) -> SurveyProject | None:
    try:
        normalized_id = int(project_id)
    except (TypeError, ValueError):
        return None
    result = await db.execute(
        select(SurveyProject).where(
            SurveyProject.id == normalized_id,
            SurveyProject.profile_id == profile_id,
        )
    )
    return result.scalar_one_or_none()


PHASE_LABELS = {
    "pre_survey": "调查前（问卷设计/方法论规划阶段）",
    "during_survey": "调查中（田野访谈实施阶段）",
    "post_survey": "调查后（数据分析/成果导出阶段）",
}

# Compact dimension labels for spectrum summary (kept for fine-grained AI context)
SPECTRUM_LABELS = [
    ("theory_driven", "理论↔经验"), ("methodological_rigidity", "严谨↔灵活"),
    ("analysis_depth", "广度↔深度"), ("structure_preference", "结构↔开放"),
    ("participation_level", "旁观↔参与"), ("tech_dependency", "低↔高技术"),
    ("writing_style", "学术↔通俗"), ("learning_preference", "示范↔自主"),
]


def _build_system_prompt(
    profile: dict | None,
    project: dict | None,
    theme: str = "academic",
    memory_context: str = "",
    extra_context: dict | None = None,
) -> str:
    """Build a context-rich system prompt using ClusterRouter fragment assembly.

    The old monolithic approach (theme_system + hardcoded label maps + spectrum
    bars) is replaced by cluster_router.assemble(), which dynamically selects
    and merges PromptFragments based on the user's identity dimensions.

    Dynamic context (project, memory, recent transcripts) is still injected
    because it cannot be pre-compiled into fragments.
    """
    # ── Core identity (immutable base) ──
    base = (
        "你是「问津」AI社会调查工作台的智能助手（Survey Copilot）。\n"
        "你的任务是帮助用户解决社会调查中遇到的问题。"
    )

    # ── Build profile for ClusterRouter ──
    profile_for_router = dict(profile) if profile else {}
    # Ensure theme_preference is set (may not be in legacy profiles)
    if theme and "theme_preference" not in profile_for_router:
        profile_for_router["theme_preference"] = theme

    # ── Assemble personalised prompt via ClusterRouter ──
    # This replaces: theme_system, output_style, role/exp/paradigm label maps,
    # and the manual spectrum visualisation.  The fragments are richer and
    # more actionable than the old one-size-fits-all blocks.
    system_prompt = cluster_router.assemble(
        profile_for_router,
        extra_context=extra_context,
        base_prompt=base,
    )

    # ── Compact spectrum summary (kept for fine-grained AI tuning) ──
    if profile:
        spec_bits = []
        for dim_id, dim_label in SPECTRUM_LABELS:
            val = profile.get(dim_id)
            if val is not None:
                spec_bits.append(f"{dim_label}={val}")
        if spec_bits:
            system_prompt += (
                "\n\n## 方法论光谱\n"
                + "，".join(spec_bits)
                + "（1-5标度，请据此微调建议深度与风格）"
            )

    # ── Inject user memories (Hermes-style) ──
    if memory_context:
        system_prompt += "\n\n" + memory_context

    # ── Dynamic project context ──
    if project:
        proj_lines = ["\n## 当前调查项目"]
        proj_lines.append(f"- 项目名称: {project.get('title', '未命名')}")
        if project.get("research_direction"):
            proj_lines.append(f"- 研究方向: {project['research_direction']}")
        phase = project.get("phase", "pre_survey")
        proj_lines.append(f"- 当前阶段: {PHASE_LABELS.get(phase, phase)}")
        proj_lines.append(f"- 研究范式: {project.get('paradigm', 'qualitative')}")
        system_prompt += "\n" + "\n".join(proj_lines)

    # ── Closing instructions ──
    system_prompt += (
        "\n\n请根据以上上下文，提供专业、有针对性的回答。"
        "\n如果用户的问题需要更多背景信息，请主动询问。"
        "\n所有回答用中文，Markdown格式。"
    )

    return system_prompt


@router.post("/chat/stream")
async def copilot_chat_stream(
    payload: dict,
    profile: UserProfile = Depends(get_current_profile),
    ai: AIService = Depends(get_ai_service),
    db: AsyncSession = Depends(get_db),
):
    """Stream a copilot response with full survey context injection."""
    message = payload.get("message", "").strip()
    if not message:
        return StreamingResponse(
            iter(["data: {\"error\": \"message is required\"}\n\n"]),
            media_type="text/event-stream",
        )

    theme = payload.get("theme", "academic")
    project_id = payload.get("project_id")
    project_context_id = None
    extra_context = payload.get("extra_context", "")

    profile_data = None
    project_data = None
    recent_sessions = []

    # Build profile_data from the authenticated profile directly
    profile_data = {
        "role": profile.role, "experience_level": profile.experience_level,
        "paradigm_preference": profile.paradigm_preference,
        "scenario_preference": profile.scenario_preference,
        "theme_preference": profile.theme_preference,
        "theory_driven": profile.theory_driven,
        "methodological_rigidity": profile.methodological_rigidity,
        "analysis_depth": profile.analysis_depth,
        "structure_preference": profile.structure_preference,
        "participation_level": profile.participation_level,
        "tech_dependency": profile.tech_dependency,
        "writing_style": profile.writing_style,
        "learning_preference": profile.learning_preference,
    }

    if project_id:
        proj = await _owned_project(db, project_id, profile.id)
        if proj is None:
            async def error_stream():
                yield 'data: {"error": "Project not found"}\n\n'

            return StreamingResponse(error_stream(), media_type="text/event-stream")
        project_data = {
            "title": proj.title,
            "research_direction": proj.research_direction,
            "phase": proj.phase,
            "paradigm": proj.paradigm,
        }
        project_context_id = proj.id
        session_rows = await db.execute(
            select(SurveySession)
            .where(SurveySession.project_id == proj.id)
            .order_by(SurveySession.id.desc())
            .limit(3)
        )
        for s in session_rows.scalars().all():
            if s.transcript_text:
                snippet = s.transcript_text[-500:] if len(s.transcript_text or "") > 500 else s.transcript_text
                recent_sessions.append(snippet)

    # ── Retrieve user memories (Hermes-style) ──
    memory_context = ""
    try:
        memories = await MemoryService.get_relevant_memories(db, profile.id, message)
        memory_context = MemoryService.build_memory_context(memories)
    except Exception as e:
        logger.warning("Memory retrieval failed: %s", e)

    system_prompt = _build_system_prompt(profile_data, project_data, theme, memory_context)

    user_content = message
    if extra_context:
        user_content = f"## 当前页面附加信息\n{extra_context}\n\n## 用户问题\n{message}"
    if recent_sessions:
        session_context = "\n\n".join(
            f"[历史访谈片段 {i+1}]\n{t}" for i, t in enumerate(recent_sessions)
        )
        user_content = f"## 最近的访谈记录\n{session_context}\n\n{user_content}"

    if profile.id not in conversation_history:
        conversation_history[profile.id] = []
    history = conversation_history[profile.id]

    sys_msg = {"role": "system", "content": system_prompt}
    messages = [sys_msg] + history[-MAX_HISTORY:] + [{"role": "user", "content": user_content}]

    async def event_stream():
        full_response = []
        try:
            async for token in ai.chat_stream(
                messages, temperature=0.7, max_tokens=4096, task="guidance"
            ):
                full_response.append(token)
                yield f"data: {json.dumps({'token': token})}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.exception("Copilot stream error")
            yield f"data: {json.dumps({'error': 'AI service unavailable'})}\n\n"
        else:
            history.append({"role": "user", "content": message})
            history.append({"role": "assistant", "content": "".join(full_response)})
            if len(history) > MAX_HISTORY * 2:
                conversation_history[profile.id] = history[-(MAX_HISTORY * 2):]

        # ── Post-dialogue memory extraction (Hermes-style) ──
        if full_response:
            try:
                assistant_reply = "".join(full_response)
                extracted = await MemoryService.extract_from_dialogue(
                    ai, message, assistant_reply, profile_data,
                )
                if extracted:
                    await WISEService.create_memory_proposals(
                        db,
                        profile.id,
                        extracted,
                        source="ai",
                        project_id=project_context_id,
                    )
            except Exception as e:
                logger.warning("Post-dialogue memory extraction failed: %s", e)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/chat")
async def copilot_chat(
    payload: dict,
    profile: UserProfile = Depends(get_current_profile),
    ai: AIService = Depends(get_ai_service),
    db: AsyncSession = Depends(get_db),
):
    """Non-streaming copilot chat (for quick queries)."""
    message = payload.get("message", "").strip()
    if not message:
        return {"error": "message is required"}

    theme = payload.get("theme", "academic")
    project_id = payload.get("project_id")
    project_context_id = None

    profile_data = None
    project_data = None

    # Build profile_data from the authenticated profile directly
    profile_data = {
        "role": profile.role, "experience_level": profile.experience_level,
        "paradigm_preference": profile.paradigm_preference,
        "scenario_preference": profile.scenario_preference,
        "theme_preference": profile.theme_preference,
        "theory_driven": profile.theory_driven,
        "methodological_rigidity": profile.methodological_rigidity,
        "analysis_depth": profile.analysis_depth,
        "structure_preference": profile.structure_preference,
        "participation_level": profile.participation_level,
        "tech_dependency": profile.tech_dependency,
        "writing_style": profile.writing_style,
        "learning_preference": profile.learning_preference,
    }

    if project_id:
        proj = await _owned_project(db, project_id, profile.id)
        if proj is None:
            return {"error": "Project not found"}
        project_data = {
            "title": proj.title,
            "research_direction": proj.research_direction,
            "phase": proj.phase,
            "paradigm": proj.paradigm,
        }
        project_context_id = proj.id

    # ── Retrieve user memories ──
    memory_context = ""
    try:
        memories = await MemoryService.get_relevant_memories(db, profile.id, message)
        memory_context = MemoryService.build_memory_context(memories)
    except Exception as e:
        logger.warning("Memory retrieval failed: %s", e)

    system_prompt = _build_system_prompt(profile_data, project_data, theme, memory_context)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": message},
    ]
    result = await ai.chat(messages, temperature=0.7, max_tokens=4096, task="guidance")

    # ── Post-dialogue memory extraction ──
    if result:
        try:
            extracted = await MemoryService.extract_from_dialogue(
                ai, message, result, profile_data,
            )
            if extracted:
                await WISEService.create_memory_proposals(
                    db,
                    profile.id,
                    extracted,
                    source="ai",
                    project_id=project_context_id,
                )
        except Exception as e:
            logger.warning("Post-dialogue memory extraction failed: %s", e)

    return {"reply": result}
