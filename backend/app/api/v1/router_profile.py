"""Profile and identity endpoints — user profiling with AI methodology guidance.

Includes Quick Profile extraction: users provide a short keyword-based
description and the AI infers structured profile fields automatically.
"""

import json
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_ai_service, get_db
from app.api.deps_auth import get_current_profile
from app.models.survey import UserProfile
from app.services.ai import AIService
from app.skills.mode_prompts import build_spectrum_prompt, build_enhanced_system_prompt

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("/defaults")
async def get_profile_defaults():
    return {
        "modes": [
            {"id": "personal", "label": "个人模式"},
            {"id": "team", "label": "团队模式"},
        ],
        "genders": [
            {"id": "male", "label": "男"},
            {"id": "female", "label": "女"},
            {"id": "non_binary", "label": "非二元"},
            {"id": "prefer_not", "label": "不愿透露"},
        ],
        "roles": [
            {"id": "undergraduate", "label": "本科生"},
            {"id": "graduate", "label": "硕士研究生"},
            {"id": "phd_candidate", "label": "博士研究生"},
            {"id": "researcher", "label": "研究人员"},
            {"id": "faculty", "label": "教师"},
            {"id": "practitioner", "label": "实务工作者"},
            {"id": "other", "label": "其他"},
        ],
        "experience_levels": [
            {"id": "beginner", "label": "新手（第一次做调查）"},
            {"id": "intermediate", "label": "有一定经验（做过1-3次）"},
            {"id": "advanced", "label": "经验丰富（4次以上）"},
        ],
        "age_ranges": [
            {"id": "18_25", "label": "18-25岁"},
            {"id": "26_35", "label": "26-35岁"},
            {"id": "36_45", "label": "36-45岁"},
            {"id": "46_plus", "label": "46岁以上"},
            {"id": "prefer_not", "label": "不愿透露"},
        ],
        "paradigms": [
            {"id": "qualitative", "label": "质性研究"},
            {"id": "quantitative", "label": "量化研究"},
            {"id": "mixed", "label": "混合方法"},
        ],
        "scenarios": [
            {"id": "community_interview", "label": "社区访谈"},
            {"id": "rural_fieldwork", "label": "乡村田野"},
            {"id": "questionnaire_survey", "label": "问卷调研"},
            {"id": "online_survey", "label": "在线调查"},
            {"id": "other", "label": "其他场景"},
        ],
        "themes": [
            {"id": "academic", "label": "学术风格（深蓝+金色，适合高校师生）"},
            {"id": "government", "label": "政务风格（红色+白色，适合党政机关）"},
            {"id": "youth", "label": "青春风格（蓝白+圆角，适合大学生）"},
        ],
    }



def _profile_to_dict(profile: UserProfile) -> dict:
    return {
        "id": profile.id, "user_id": profile.user_id,
        "mode": profile.mode, "gender": profile.gender,
        "role": profile.role, "experience_level": profile.experience_level,
        "age_range": profile.age_range, "mbti": profile.mbti,
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
        "ai_temperature": profile.ai_temperature,
        "ai_model_pref": profile.ai_model_pref,
        "ai_hint_frequency": profile.ai_hint_frequency,
        "ui_font_size": profile.ui_font_size,
        "ui_high_contrast": profile.ui_high_contrast,
        "default_export_format": profile.default_export_format,
        "auto_save_interval": profile.auto_save_interval,
    }

@router.post("")
async def update_my_profile(
    payload: dict,
    profile: UserProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    """Update the current user's profile."""
    for field in ["mode", "gender", "role", "experience_level", "age_range", "mbti",
                    "paradigm_preference", "scenario_preference", "theme_preference",
                    # Spectrum dimensions
                    "theory_driven", "methodological_rigidity", "analysis_depth",
                    "structure_preference", "participation_level", "tech_dependency",
                    "writing_style", "learning_preference",
                    # User settings
                    "ai_temperature", "ai_model_pref", "ai_hint_frequency",
                    "ui_font_size", "ui_high_contrast", "default_export_format",
                    "auto_save_interval"]:
        if field in payload:
            setattr(profile, field, payload[field])

    await db.commit()
    await db.refresh(profile)
    return {
        "id": profile.id,
        "mode": profile.mode,
        "gender": profile.gender,
        "role": profile.role,
        "experience_level": profile.experience_level,
        "age_range": profile.age_range,
        "mbti": profile.mbti,
        "paradigm_preference": profile.paradigm_preference,
        "scenario_preference": profile.scenario_preference,
        "theme_preference": profile.theme_preference,
        # Spectrum
        "theory_driven": profile.theory_driven,
        "methodological_rigidity": profile.methodological_rigidity,
        "analysis_depth": profile.analysis_depth,
        "structure_preference": profile.structure_preference,
        "participation_level": profile.participation_level,
        "tech_dependency": profile.tech_dependency,
        "writing_style": profile.writing_style,
        "learning_preference": profile.learning_preference,
        # Settings
        "ai_temperature": profile.ai_temperature,
        "ai_model_pref": profile.ai_model_pref,
        "ai_hint_frequency": profile.ai_hint_frequency,
        "ui_font_size": profile.ui_font_size,
        "ui_high_contrast": profile.ui_high_contrast,
        "default_export_format": profile.default_export_format,
        "auto_save_interval": profile.auto_save_interval,
    }



@router.get("/me")
async def get_my_profile(
    profile: UserProfile = Depends(get_current_profile),
):
    """Get the current user's profile (resolved from JWT)."""
    return _profile_to_dict(profile)

@router.get("/{profile_id}")
async def get_profile(
    profile_id: int,
    profile: UserProfile = Depends(get_current_profile),
):
    """Get profile by ID (only own profile)."""
    if profile.id != profile_id:
        return {"error": "Profile not found"}
    return _profile_to_dict(profile)
@router.post("/guidance")
async def get_profile_guidance(payload: dict, ai: AIService = Depends(get_ai_service)):
    """Generate methodology guidance based on comprehensive user profile."""
    role_map = {
        "undergraduate": "本科生", "graduate": "硕士���究生", "phd_candidate": "博士研究生",
        "researcher": "研究人员", "faculty": "教师", "practitioner": "实务工作者", "other": "其他",
    }
    exp_map = {"beginner": "新手（第一次做调查）", "intermediate": "有一定经验", "advanced": "经验丰富"}
    paradigm_map = {"qualitative": "质性研究", "quantitative": "量化研究", "mixed": "混合方法"}
    scenario_map = {
        "community_interview": "社区访谈", "rural_fieldwork": "乡村田野",
        "questionnaire_survey": "问卷调研", "online_survey": "在线调查", "other": "其他场景",
    }

    profile_text = (
        f"身份: {role_map.get(payload.get('role', 'undergraduate'), '本科生')}\n"
        f"经验水平: {exp_map.get(payload.get('experience_level', 'beginner'), '新手')}\n"
        f"年龄范围: {payload.get('age_range', '未提供')}\n"
        f"性别: {payload.get('gender', '未提供')}\n"
        f"MBTI: {payload.get('mbti', '未提供')}\n"
        f"研究范式偏好: {paradigm_map.get(payload.get('paradigm_preference', 'qualitative'), '质性')}\n"
        f"调查场景: {scenario_map.get(payload.get('scenario_preference', 'community_interview'), '社区访谈')}\n"
        f"工作模式: {payload.get('mode', 'personal')}\n"
    )

    # Build spectrum prompt if spectrum values provided
    spectrum_dims = {
        dim: payload.get(dim) for dim in [
            "theory_driven", "methodological_rigidity", "analysis_depth",
            "structure_preference", "participation_level", "tech_dependency",
            "writing_style", "learning_preference",
        ] if dim in payload
    }
    spectrum_text = build_spectrum_prompt(spectrum_dims) if spectrum_dims else ""

    prompt = (
        f"用户画像:\n{profile_text}\n{spectrum_text}\n\n"
        "请根据以上用户画像（包括方法论光谱定位），生成个性化的社会调查研究方法论指导。包括：\n"
        "1. **适合你的调查方法**：根据你的身份、经验水平和光谱位置，推荐最合适的调查方法组合\n"
        "2. **常见误区和应对**：你这个阶段最容易犯的错误及预防策略\n"
        "3. **推荐流程**：从选题到报告的分步骤流程（考虑你的时间和资源约束）\n"
        "4. **伦理注意事项**：针对你的场景的特殊伦理考虑\n"
        "5. **工具推荐**：适合你当前水平的软硬件工具\n"
        "6. **成长建议**：如何通过这次调查提升你的方法论能力\n"
        "用中文输出，Markdown格式，语气亲和但有学术深度。"
    )
    messages = [
        {"role": "system", "content": "你是一位经验丰富的社会调查导师，擅长根据研究者的个人特征（包括方法论光谱位置）提供差异化的方法论指导。你的建议既有理论依据又注重可操作性。"},
        {"role": "user", "content": prompt},
    ]
    result = await ai.chat(messages, temperature=0.7, max_tokens=8192, task="guidance")
    return {"guidance": result}


@router.post("/guidance/stream")
async def get_profile_guidance_stream(payload: dict, ai: AIService = Depends(get_ai_service)):
    """Generate methodology guidance with SSE streaming response."""
    role_map = {
        "undergraduate": "本科生", "graduate": "硕士研究生", "phd_candidate": "博士研究生",
        "researcher": "研究人员", "faculty": "教师", "practitioner": "实务工作者", "other": "其他",
    }
    exp_map = {"beginner": "新手（第一次做调查）", "intermediate": "有一定经验", "advanced": "经验丰富"}
    paradigm_map = {"qualitative": "质性研究", "quantitative": "量化研究", "mixed": "混合方法"}
    scenario_map = {
        "community_interview": "社区访谈", "rural_fieldwork": "乡村田野",
        "questionnaire_survey": "问卷调研", "online_survey": "在线调查", "other": "其他场景",
    }

    profile_text = (
        f"身份: {role_map.get(payload.get('role', 'undergraduate'), '本科生')}\n"
        f"经验水平: {exp_map.get(payload.get('experience_level', 'beginner'), '新手')}\n"
        f"年龄范围: {payload.get('age_range', '未提供')}\n"
        f"性别: {payload.get('gender', '未提供')}\n"
        f"MBTI: {payload.get('mbti', '未提供')}\n"
        f"研究范式偏好: {paradigm_map.get(payload.get('paradigm_preference', 'qualitative'), '质性')}\n"
        f"调查场景: {scenario_map.get(payload.get('scenario_preference', 'community_interview'), '社区访谈')}\n"
        f"工作模式: {payload.get('mode', 'personal')}\n"
    )

    # Build spectrum prompt
    spectrum_dims2 = {
        dim: payload.get(dim) for dim in [
            "theory_driven", "methodological_rigidity", "analysis_depth",
            "structure_preference", "participation_level", "tech_dependency",
            "writing_style", "learning_preference",
        ] if dim in payload
    }
    spectrum_text2 = build_spectrum_prompt(spectrum_dims2) if spectrum_dims2 else ""

    prompt = (
        f"用户画像:\n{profile_text}\n{spectrum_text2}\n\n"
        "请根据以上用户画像（包括方法论光谱定位），生成个性化的社会调查研究方法论指导。包括：\n"
        "1. **适合你的调查方法**：根据你的身份、经验水平和光谱位置，推荐最合适的调查方法组合\n"
        "2. **常见误区和应对**：你这个阶段最容易犯的错误及预防策略\n"
        "3. **推荐流程**：从选题到报告的分步骤流程（考虑你的时间和资源约束）\n"
        "4. **伦理注意事项**：针对你的场景的特殊伦理考虑\n"
        "5. **工具推荐**：适合你当前水平的软硬件工具\n"
        "6. **成长建议**：如何通过这次调查提升你的方法论能力\n"
        "用中文输出，Markdown格式，语气亲和但有学术深度。"
    )
    messages = [
        {"role": "system", "content": "你是一位经验丰富的社会调查导师，擅长根据研究者的个人特征（包括方法论光谱位置）提供差异化的方法论指导。你的建议既有理论依据又注重可操作性。"},
        {"role": "user", "content": prompt},
    ]

    async def event_stream():
        async for token in ai.chat_stream(messages, temperature=0.7, max_tokens=8192, task="guidance"):
            yield f"data: {json.dumps({'token': token})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ── Quick Profile: AI-powered profile extraction from free-text description ──

QUICK_PROFILE_SYSTEM_PROMPT = """你是一个社会调查用户画像分析专家。根据用户提供的简短自我描述，提取出结构化的用户画像信息。

用户描述可能包含：身份角色、研究兴趣、经验水平、性格偏好、工作风格等关键词或自由叙述。

你需要输出一个严格的JSON对象（不要markdown代码块），包含以下字段。对于无法从描述中推断的字段，使用合理的默认值（role默认"undergraduate"，experience_level默认"beginner"，paradigm_preference默认"qualitative"，scenario_preference默认"community_interview"，spectrum维度默认3）。

JSON Schema:
{
  "mode": "personal 或 team",
  "gender": "male / female / non_binary / prefer_not",
  "role": "undergraduate / graduate / phd_candidate / researcher / faculty / practitioner / other",
  "experience_level": "beginner / intermediate / advanced",
  "age_range": "18_25 / 26_35 / 36_45 / 46_plus / prefer_not",
  "mbti": "推断的MBTI类型或空字符串",
  "paradigm_preference": "qualitative / quantitative / mixed",
  "scenario_preference": "community_interview / rural_fieldwork / questionnaire_survey / online_survey / other",
  "theme_preference": "academic / government / youth",
  "theory_driven": 1-5 (1=理论驱动, 5=经验驱动, 默认3),
  "methodological_rigidity": 1-5 (1=严谨规范, 5=灵活探索, 默认3),
  "analysis_depth": 1-5 (1=广度优先, 5=深度优先, 默认3),
  "structure_preference": 1-5 (1=结构化, 5=开放式, 默认3),
  "participation_level": 1-5 (1=旁观观察, 5=深度参与, 默认3),
  "tech_dependency": 1-5 (1=低技术, 5=高技术, 默认3),
  "writing_style": 1-5 (1=学术正式, 5=通俗亲和, 默认3),
  "learning_preference": 1-5 (1=示范引导, 5=自主探索, 默认3),
  "profile_summary": "一句话总结用户画像（50字内）",
  "extraction_confidence": 0.0-1.0 (整体提取置信度)
}

推理原则：
- 如果用户说"我是博士生/在做博士论文" → role=phd_candidate, experience_level≥intermediate
- 如果用户提到"定量/数据/统计/回归" → paradigm_preference=quantitative
- 如果用户提到"访谈/田野/质性/参与观察" → paradigm_preference=qualitative
- 如果用户提到"混合/多元" → paradigm_preference=mixed
- 如果用户说"第一次/没经验/新手" → experience_level=beginner
- 如果用户说"做过几次/有一些经验" → experience_level=intermediate
- 如果用户说"做了很多年/经验丰富/老手" → experience_level=advanced
- 从用户的表达风格推断spectrum维度：语言正式→theory_driven偏低(偏理论)、表达灵活口语化→writing_style偏高(偏通俗)
- MBTI从用户自我描述中的工作风格和性格倾向推断"""


@router.post("/quick-profile")
async def extract_quick_profile(
    payload: dict,
    ai: AIService = Depends(get_ai_service),
):
    """Extract structured profile from a free-text self-description.

    User provides a short keyword-based description (e.g. "我是社会学博士生，
    做过3次田野调查，喜欢用访谈和问卷结合的方式做质性研究"),
    and the AI returns structured profile fields ready for review.

    The caller can then POST the returned fields to /profile to save.
    """
    description = (payload.get("description") or "").strip()
    if not description:
        return {"error": "请提供一段自我描述文本（至少10个字）"}
    if len(description) < 10:
        return {"error": "描述太短，请至少写10个字，包含你的身份、研究兴趣或工作风格"}

    user_prompt = f"用户自我描述: \"{description[:1200]}\"\n\n请提取结构化画像JSON。只输出JSON对象。"

    messages = [
        {"role": "system", "content": QUICK_PROFILE_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    try:
        raw = await ai.chat(messages, temperature=0.3, max_tokens=1024, task="analysis")
        # Parse AI response — strip markdown code fences if present
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        data = json.loads(text)

        # Build a clean result with all expected fields + defaults
        result = {
            "mode": data.get("mode", "personal"),
            "gender": data.get("gender", "prefer_not"),
            "role": data.get("role", "undergraduate"),
            "experience_level": data.get("experience_level", "beginner"),
            "age_range": data.get("age_range", "prefer_not"),
            "mbti": data.get("mbti", ""),
            "paradigm_preference": data.get("paradigm_preference", "qualitative"),
            "scenario_preference": data.get("scenario_preference", "community_interview"),
            "theme_preference": data.get("theme_preference", "academic"),
            # Spectrum dimensions (clamped to 1-5)
            "theory_driven": max(1, min(5, int(data.get("theory_driven", 3)))),
            "methodological_rigidity": max(1, min(5, int(data.get("methodological_rigidity", 3)))),
            "analysis_depth": max(1, min(5, int(data.get("analysis_depth", 3)))),
            "structure_preference": max(1, min(5, int(data.get("structure_preference", 3)))),
            "participation_level": max(1, min(5, int(data.get("participation_level", 3)))),
            "tech_dependency": max(1, min(5, int(data.get("tech_dependency", 3)))),
            "writing_style": max(1, min(5, int(data.get("writing_style", 3)))),
            "learning_preference": max(1, min(5, int(data.get("learning_preference", 3)))),
            "profile_summary": data.get("profile_summary", ""),
            "extraction_confidence": float(data.get("extraction_confidence", 0.5)),
        }
        logger.info(
            f"Quick profile extracted: role={result['role']}, "
            f"paradigm={result['paradigm_preference']}, "
            f"confidence={result['extraction_confidence']:.2f}"
        )
        return result

    except (json.JSONDecodeError, ValueError, TypeError) as e:
        logger.warning(f"Quick profile AI response parse failed: {e}")
        # Return a best-effort fallback — extract what we can from the raw text
        return {
            "mode": "personal",
            "gender": "prefer_not",
            "role": "undergraduate",
            "experience_level": "beginner",
            "age_range": "prefer_not",
            "mbti": "",
            "paradigm_preference": "qualitative",
            "scenario_preference": "community_interview",
            "theme_preference": "academic",
            "theory_driven": 3, "methodological_rigidity": 3,
            "analysis_depth": 3, "structure_preference": 3,
            "participation_level": 3, "tech_dependency": 3,
            "writing_style": 3, "learning_preference": 3,
            "profile_summary": "",
            "extraction_confidence": 0.0,
            "parse_error": True,
            "raw_response_snippet": raw[:200] if 'raw' in dir() else "",
        }


# ── Quick Keywords: AI-powered profile extraction from 3-5 keywords ──

QUICK_KEYWORDS_SYSTEM_PROMPT = """你是一个社会调查用户画像分析专家。用户会提供3-5个中文关键词来描述自己的学术身份和研究特征，你需要根据这些关键词推断出结构化的用户画像信息。

关键词通常是：身份标签（如"博士生"、"青年教师"、"研究员"）、方法偏好（如"定量"、"质性"、"田野调查"、"问卷"）、研究领域（如"社会学"、"社区治理"、"组织行为"）、工作风格（如"严谨"、"灵活"、"技术流"）等。

你需要输出一个严格的JSON对象（不要markdown代码块），包含以下字段。对于无法从关键词推断的字段，使用合理的默认值（role默认"undergraduate"，experience_level默认"beginner"，paradigm_preference默认"qualitative"，scenario_preference默认"community_interview"，spectrum维度默认3）。

JSON Schema:
{
  "mode": "personal 或 team",
  "gender": "male / female / non_binary / prefer_not",
  "role": "undergraduate / graduate / phd_candidate / researcher / faculty / practitioner / other",
  "experience_level": "beginner / intermediate / advanced",
  "age_range": "18_25 / 26_35 / 36_45 / 46_plus / prefer_not",
  "mbti": "推断的MBTI类型或空字符串",
  "paradigm_preference": "qualitative / quantitative / mixed",
  "scenario_preference": "community_interview / rural_fieldwork / questionnaire_survey / online_survey / other",
  "theme_preference": "academic / government / youth",
  "theory_driven": 1-5 (1=理论驱动, 5=经验驱动, 默认3),
  "methodological_rigidity": 1-5 (1=严谨规范, 5=灵活探索, 默认3),
  "analysis_depth": 1-5 (1=广度优先, 5=深度优先, 默认3),
  "structure_preference": 1-5 (1=结构化, 5=开放式, 默认3),
  "participation_level": 1-5 (1=旁观观察, 5=深度参与, 默认3),
  "tech_dependency": 1-5 (1=低技术, 5=高技术, 默认3),
  "writing_style": 1-5 (1=学术正式, 5=通俗亲和, 默认3),
  "learning_preference": 1-5 (1=示范引导, 5=自主探索, 默认3),
  "profile_summary": "根据关键词综合推断的一句话用户画像（50字内）",
  "extraction_confidence": 0.0-1.0 (整体提取置信度，关键词越明确、越互洽，置信度越高)
}

关键词推理规则（按优先级从高到低）：
【身份标签 → role + experience_level】
- "博士生/博士/PhD/博论/开题" → role=phd_candidate, experience_level≥intermediate
- "硕士/研究生/研二/研三/硕士论文" → role=graduate, experience_level≥beginner
- "本科/大三/大四/毕业论文" → role=undergraduate, experience_level=beginner
- "青年教师/讲师/AP/助理教授" → role=faculty, experience_level≥intermediate
- "教授/副教授/博导" → role=faculty, experience_level=advanced
- "研究员/研究所/智库" → role=researcher
- "社工/实务/一线/社区工作者" → role=practitioner
- "新手/第一次/刚入门/小白" → experience_level=beginner
- "老手/多年/资深/丰富经验" → experience_level=advanced

【方法偏好 → paradigm_preference + scenario_preference + spectrum】
- "定量/量化/统计/回归/数据/问卷/量表/SPSS/Stata/R语言" → paradigm_preference=quantitative, tech_dependency≥4, scenario_preference=questionnaire_survey
- "质性/定性/访谈/田野/参与观察/民族志/口述史/扎根理论" → paradigm_preference=qualitative, participation_level≥4, scenario_preference可设为rural_fieldwork或community_interview
- "混合方法/混合研究/多元方法/三角互证" → paradigm_preference=mixed, methodological_rigidity=3
- "问卷/调查/抽样/线上" → scenario_preference=questionnaire_survey或online_survey
- "田野/乡村/农村/社区/驻村" → scenario_preference=rural_fieldwork或community_interview
- "社区/街道/居委会/邻里" → scenario_preference=community_interview
- "网络/在线/互联网/数字" → scenario_preference=online_survey, tech_dependency≥4

【研究领域 → theme_preference + 辅助推断】
- "政务/政府/公共管理/政策/党建/治理" → theme_preference=government, writing_style≤2(偏正式)
- "学术/理论/学科/论文" → theme_preference=academic, writing_style≤2(偏学术)
- "青年/大学生/校园/Z世代" → theme_preference=youth, age_range可推测为18_25或26_35

【工作风格 → spectrum微调】
- "严谨/规范/系统/结构化/条理" → methodological_rigidity≤2(偏严谨), structure_preference≤2(偏结构化)
- "灵活/开放/探索/自由/创意" → methodological_rigidity≥4(偏灵活), structure_preference≥4(偏开放式)
- "技术/编程/Python/AI/工具/自动化" → tech_dependency≥4, learning_preference≥4(偏自主)
- "理论/概念/框架/文献" → theory_driven≤2(偏理论)
- "实践/经验/应用/行动/干预" → theory_driven≥4(偏经验)
- "深度/聚焦/个案/深耕" → analysis_depth≥4(偏深度)
- "广度/比较/大规模/全域" → analysis_depth≤2(偏广度)
- "亲和/通俗/大众/科普" → writing_style≥4(偏通俗)
- "正式/学术/规范/严谨写作" → writing_style≤2(偏学术)

【MBTI推断（谨慎，confidence低时留空）】
- "严谨+结构化+计划" → 可能J型；"灵活+开放+随性" → 可能P型
- "理论+抽象+概念" → 可能N型；"实践+具体+经验" → 可能S型
- 只有关键词明确暗示性格特征时才推断MBTI，否则留空

综合推理原则：
1. 关键词之间可能互相印证或矛盾。互相印证时提高confidence；矛盾时降低confidence并优先取更明确的关键词
2. 3个关键词时confidence一般不超过0.75；4-5个且高度互洽时可达0.85-0.95
3. profile_summary必须综合所有关键词生成，体现它们之间的逻辑关联"""


@router.post("/quick-keywords")
async def extract_quick_keywords(
    payload: dict,
    ai: AIService = Depends(get_ai_service),
):
    """Extract structured profile from 3-5 character keywords.

    User provides 3-5 keywords (e.g. ["博士生", "田野调查", "质性研究", "社区"]),
    and the AI returns structured profile fields ready for review.

    This replaces the free-text /quick-profile endpoint per 师门组会 feedback:
    keywords are faster to input and less prone to AI hallucination.
    """
    keywords: list[str] = payload.get("keywords") or []
    # Filter out empty strings
    keywords = [k.strip() for k in keywords if k and k.strip()]

    if len(keywords) < 3:
        return {"error": "请至少输入3个关键词，例如：博士生、田野调查、质性研究"}
    if len(keywords) > 5:
        keywords = keywords[:5]  # Silently truncate

    # Validate individual keyword length
    for kw in keywords:
        if len(kw) < 1:
            return {"error": "关键词不能为空"}
        if len(kw) > 15:
            return {"error": f"关键词「{kw}」过长，请控制在15字以内"}

    kw_list = "、".join(keywords)
    user_prompt = f"用户关键词: {kw_list}\n\n请根据这些关键词推断结构化画像JSON。只输出JSON对象。"

    messages = [
        {"role": "system", "content": QUICK_KEYWORDS_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    try:
        raw = await ai.chat(messages, temperature=0.3, max_tokens=1024, task="analysis")
        # Parse AI response — strip markdown code fences if present
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        data = json.loads(text)

        # Build a clean result with all expected fields + defaults
        result = {
            "mode": data.get("mode", "personal"),
            "gender": data.get("gender", "prefer_not"),
            "role": data.get("role", "undergraduate"),
            "experience_level": data.get("experience_level", "beginner"),
            "age_range": data.get("age_range", "prefer_not"),
            "mbti": data.get("mbti", ""),
            "paradigm_preference": data.get("paradigm_preference", "qualitative"),
            "scenario_preference": data.get("scenario_preference", "community_interview"),
            "theme_preference": data.get("theme_preference", "academic"),
            # Spectrum dimensions (clamped to 1-5)
            "theory_driven": max(1, min(5, int(data.get("theory_driven", 3)))),
            "methodological_rigidity": max(1, min(5, int(data.get("methodological_rigidity", 3)))),
            "analysis_depth": max(1, min(5, int(data.get("analysis_depth", 3)))),
            "structure_preference": max(1, min(5, int(data.get("structure_preference", 3)))),
            "participation_level": max(1, min(5, int(data.get("participation_level", 3)))),
            "tech_dependency": max(1, min(5, int(data.get("tech_dependency", 3)))),
            "writing_style": max(1, min(5, int(data.get("writing_style", 3)))),
            "learning_preference": max(1, min(5, int(data.get("learning_preference", 3)))),
            "profile_summary": data.get("profile_summary", ""),
            "extraction_confidence": float(data.get("extraction_confidence", 0.5)),
        }
        logger.info(
            f"Quick keywords extracted: keywords={kw_list}, "
            f"role={result['role']}, paradigm={result['paradigm_preference']}, "
            f"confidence={result['extraction_confidence']:.2f}"
        )
        return result

    except (json.JSONDecodeError, ValueError, TypeError) as e:
        logger.warning(f"Quick keywords AI response parse failed: {e}")
        return {
            "mode": "personal",
            "gender": "prefer_not",
            "role": "undergraduate",
            "experience_level": "beginner",
            "age_range": "prefer_not",
            "mbti": "",
            "paradigm_preference": "qualitative",
            "scenario_preference": "community_interview",
            "theme_preference": "academic",
            "theory_driven": 3, "methodological_rigidity": 3,
            "analysis_depth": 3, "structure_preference": 3,
            "participation_level": 3, "tech_dependency": 3,
            "writing_style": 3, "learning_preference": 3,
            "profile_summary": "",
            "extraction_confidence": 0.0,
            "parse_error": True,
            "raw_response_snippet": raw[:200] if 'raw' in dir() else "",
        }
    except Exception:
        logger.exception("Quick keywords AI service call failed")
        return {"error": "AI服务调用失败，请稍后重试。"}
