"""Analysis endpoints — AI-powered data analysis for post-survey phase."""

import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_ai_service, get_db
from app.api.deps_auth import get_current_profile
from app.models.survey import AnalysisResult, SurveyProject, UserProfile
from app.services.ai import AIService
from app.services.sociobench import sociobench_kb
from app.skills.mode_prompts import (
    get_mode_analysis_frameworks,
    get_mode_modifier,
    get_distilled_task_prompt,
    get_mode_task_config,
)

router = APIRouter(tags=["analysis"])


def _build_analysis_system_prompt(theme: str = "academic") -> str:
    """Build a mode-aware analysis system prompt with appropriate frameworks."""
    parts = ["你是一位社会科学数据分析专家，精通量化统计和质性分析。善于利用ISSP等国际调查数据作为参照基准。"]

    mode_sys = get_mode_modifier(theme, "system")
    if mode_sys:
        parts.append(mode_sys)

    frameworks = get_mode_analysis_frameworks(theme)
    if frameworks:
        fw_lines = ["\n## 推荐分析框架"]
        for fw in frameworks:
            fw_lines.append(f"\n### {fw['name']}")
            fw_lines.append(f"{fw['desc']}")
            fw_lines.append("步骤：" + " → ".join(fw["steps"]))
        parts.append("\n".join(fw_lines))

    distilled = get_distilled_task_prompt(theme, "analysis")
    if distilled:
        parts.append(distilled)

    parts.append("输出结构化、可操作的分析报告。")
    return "\n\n".join(parts)


def _build_analysis_user_prompt(
    data_type: str, content: str, paradigm: str, theme: str,
    research_topic: str = "", include_charts: bool = False,
) -> str:
    """Build a mode-aware analysis user prompt with paradigm + theme angles."""
    paradigm_prompts = {
        "qualitative": (
            "请对以下质性数据进行系统分析：\n"
            "1. **主题分析**：识别核心主题和子主题\n"
            "2. **叙事分析**：关键叙事结构和转折点\n"
            "3. **编码分析**：开放式编码→主轴编码→选择性编码\n"
            "4. **个案比较**：跨案例的模式与差异\n"
            "5. **理论对话**：与现有理论的关联与贡献"
        ),
        "quantitative": (
            "请对以下量化数据进行分析建议：\n"
            "1. **描述性统计**：均值、标准差、分布特征\n"
            "2. **推断统计建议**：适合的检验方法（t检验/ANOVA/回归等）\n"
            "3. **效应量评估**\n"
            "4. **可视化建议**\n"
            "5. **统计结论效度**：样本量充分性、多重比较校正"
        ),
        "mixed": (
            "请对以下混合方法数据进行整合分析：\n"
            "1. **量化部分**：统计发现摘要\n"
            "2. **质性部分**：主题/叙事发现\n"
            "3. **整合分析**：量化和质性的收敛/发散\n"
            "4. **联合展示**：建议的联合显示方式\n"
            "5. **混合方法效度**：整合质量评估"
        ),
    }
    analysis_prompt = paradigm_prompts.get(paradigm, paradigm_prompts["qualitative"])
    prompt = f"数据类型: {data_type}\n数据/摘要:\n{content}\n\n{analysis_prompt}"

    if research_topic:
        socio = sociobench_kb.build_analysis_context(research_topic)
        if socio:
            prompt += socio

    mode_angles = {
        "academic": "\n\n请特别关注：理论贡献与文献对话空间、概念化水平、与ISSP国际比较数据的关联。",
        "government": "\n\n请特别关注：政策含义与可操作性、问题诊断的准确性、对策建议的具体性、利益相关方分析。",
        "youth": "\n\n请特别关注：分析过程的清晰性（便于学习者理解）、概念解释、反思性问题引导、进一步学习建议。",
    }
    if theme in mode_angles:
        prompt += mode_angles[theme]

    if include_charts:
        prompt += (
            "\n\n另外，请根据分析数据，生成1-3个ECharts图表的配置JSON。"
            "放在一个 ```chartjson 代码块中，格式为JSON数组，每个元素包含:\n"
            '- type: "bar"|"pie"|"scatter"|"line"\n'
            '- title: 图表标题\n'
            '- data: 图表数据。bar/line为{categories:[], series:[{name,data}]}；pie为[{name,value}]；scatter为[[x,y],...]\n'
        )

    return prompt


@router.get("/analysis/summary")
async def analysis_summary(
    profile: UserProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AnalysisResult)
        .join(SurveyProject, SurveyProject.id == AnalysisResult.project_id)
        .where(SurveyProject.profile_id == profile.id)
    )
    analyses = result.scalars().all()
    return {
        "total_analyses": len(analyses),
        "recent": [
            {"id": a.id, "type": a.analysis_type, "created_at": str(a.created_at) if a.created_at else None}
            for a in analyses[-5:]
        ],
        "hint": "Use POST /analysis/run to submit data for AI analysis.",
    }


@router.post("/analysis/run")
async def analysis_run(
    payload: dict,
    profile: UserProfile = Depends(get_current_profile),
    ai: AIService = Depends(get_ai_service),
    db: AsyncSession = Depends(get_db),
):
    data_type = payload.get("type", "interview")
    content = payload.get("content", "")
    paradigm = payload.get("paradigm", "qualitative")
    project_id = payload.get("project_id", 0)
    include_charts = payload.get("include_charts", False)
    research_topic = payload.get("research_topic", "")
    theme = payload.get("theme", "academic")

    if not content.strip():
        return {"error": "content is required"}
    if theme not in ("academic", "government", "youth"):
        theme = "academic"

    try:
        project_id = int(project_id or 0)
    except (TypeError, ValueError):
        project_id = 0
    if project_id:
        project_result = await db.execute(
            select(SurveyProject).where(
                SurveyProject.id == project_id,
                SurveyProject.profile_id == profile.id,
            )
        )
        if project_result.scalar_one_or_none() is None:
            return {"error": "Project not found"}

    system_prompt = _build_analysis_system_prompt(theme)
    user_prompt = _build_analysis_user_prompt(
        data_type, content, paradigm, theme, research_topic, include_charts,
    )
    task_cfg = get_mode_task_config(theme, "analysis")

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    result = await ai.chat(messages, temperature=task_cfg["temperature"], max_tokens=task_cfg["max_tokens"], task="analysis")

    if project_id:
        analysis_record = AnalysisResult(project_id=project_id, analysis_type=data_type, content=result)
        db.add(analysis_record)
        await db.commit()

    matched_domains = sociobench_kb.match_domains(research_topic, top_k=3) if research_topic else []

    return {
        "type": data_type,
        "paradigm": paradigm,
        "theme": theme,
        "analysis": result,
        "issp_domains": matched_domains,
    }


@router.post("/analysis/run/stream")
async def analysis_run_stream(payload: dict, ai: AIService = Depends(get_ai_service)):
    """Stream mode-aware AI analysis results via SSE."""
    data_type = payload.get("type", "interview")
    content = payload.get("content", "")
    paradigm = payload.get("paradigm", "qualitative")
    include_charts = payload.get("include_charts", False)
    research_topic = payload.get("research_topic", "")
    theme = payload.get("theme", "academic")

    if not content.strip():
        return {"error": "content is required"}
    if theme not in ("academic", "government", "youth"):
        theme = "academic"

    system_prompt = _build_analysis_system_prompt(theme)
    user_prompt = _build_analysis_user_prompt(
        data_type, content, paradigm, theme, research_topic, include_charts,
    )
    task_cfg = get_mode_task_config(theme, "analysis")

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    async def event_stream():
        async for token in ai.chat_stream(messages, temperature=task_cfg["temperature"], max_tokens=task_cfg["max_tokens"], task="analysis"):
            yield f"data: {json.dumps({'token': token})}\n\n"
        if research_topic:
            domains = sociobench_kb.match_domains(research_topic, top_k=3)
            yield f"data: {json.dumps({'issp_domains': domains})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
