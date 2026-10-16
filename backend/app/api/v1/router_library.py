"""Survey results library — project review, lessons learned, knowledge accumulation."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_ai_service, get_db
from app.api.deps_auth import get_current_profile
from app.models.survey import (
    AnalysisResult,
    ExportDocument,
    SurveyProject,
    SurveySession,
    UserProfile,
)
from app.services.ai import AIService

router = APIRouter(prefix="/library", tags=["library"])


@router.get("")
async def list_library(
    profile: UserProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    """List all completed or archived survey projects."""
    result = await db.execute(
        select(SurveyProject)
        .where(SurveyProject.profile_id == profile.id)
        .order_by(SurveyProject.updated_at.desc())
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
                "updated_at": str(p.updated_at) if p.updated_at else None,
            }
            for p in projects
        ]
    }


@router.get("/{project_id}")
async def get_library_item(
    project_id: int,
    profile: UserProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    """Full detail view of a past project — all phases and outputs."""
    result = await db.execute(
        select(SurveyProject).where(
            SurveyProject.id == project_id,
            SurveyProject.profile_id == profile.id,
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        return {"error": "Project not found"}

    sessions_result = await db.execute(
        select(SurveySession).where(SurveySession.project_id == project_id).order_by(SurveySession.created_at.desc())
    )
    sessions = sessions_result.scalars().all()

    analyses_result = await db.execute(
        select(AnalysisResult).where(AnalysisResult.project_id == project_id).order_by(AnalysisResult.created_at.desc())
    )
    analyses = analyses_result.scalars().all()

    exports_result = await db.execute(
        select(ExportDocument).where(ExportDocument.project_id == project_id).order_by(ExportDocument.created_at.desc())
    )
    exports = exports_result.scalars().all()

    return {
        "project": {
            "id": project.id,
            "title": project.title,
            "research_direction": project.research_direction,
            "paradigm": project.paradigm,
            "phase": project.phase,
            "status": project.status,
            "topic_argumentation": project.topic_argumentation,
            "questionnaire_design": project.questionnaire_design,
            "methodology_guidance": project.methodology_guidance,
            "created_at": str(project.created_at) if project.created_at else None,
        },
        "sessions": [
            {
                "id": s.id,
                "transcript_text": s.transcript_text,
                "summary_text": s.summary_text,
                "notes": s.notes,
                "created_at": str(s.created_at) if s.created_at else None,
            }
            for s in sessions
        ],
        "analyses": [
            {"id": a.id, "type": a.analysis_type, "content": a.content, "created_at": str(a.created_at) if a.created_at else None}
            for a in analyses
        ],
        "exports": [
            {"id": e.id, "format": e.format_type, "content": e.content, "created_at": str(e.created_at) if e.created_at else None}
            for e in exports
        ],
    }


@router.post("/{project_id}/lessons")
async def generate_lessons(
    project_id: int,
    profile: UserProfile = Depends(get_current_profile),
    ai: AIService = Depends(get_ai_service),
    db: AsyncSession = Depends(get_db),
):
    """AI-generated lessons learned from a complete project lifecycle."""
    result = await db.execute(
        select(SurveyProject).where(
            SurveyProject.id == project_id,
            SurveyProject.profile_id == profile.id,
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        return {"error": "Project not found"}

    context_parts = [f"项目名称: {project.title}"]
    if project.research_direction:
        context_parts.append(f"研究方向: {project.research_direction}")
    if project.topic_argumentation:
        context_parts.append(f"选题论证: {project.topic_argumentation[:500]}")
    if project.questionnaire_design:
        context_parts.append(f"问卷设计: {project.questionnaire_design[:500]}")

    sessions_result = await db.execute(
        select(SurveySession).where(SurveySession.project_id == project_id)
    )
    sessions = sessions_result.scalars().all()
    if sessions:
        context_parts.append(f"共进行了 {len(sessions)} 次田野访谈/调查")

    analyses_result = await db.execute(
        select(AnalysisResult).where(AnalysisResult.project_id == project_id)
    )
    analyses = analyses_result.scalars().all()
    if analyses:
        context_parts.append(f"完成了 {len(analyses)} 次分析")

    context = "\n".join(context_parts)
    prompt = (
        f"项目信息:\n{context}\n\n"
        "请基于以上项目全过程信息，为该调查项目生成经验总结：\n"
        "1. **做得好的地方**（方法论选择、执行效率、工具使用等）\n"
        "2. **可以改进的地方**（方法局限、执行偏差、遗漏的环节）\n"
        "3. **对下次调查的实用建议**（具体、可操作）\n"
        "4. **方法论层面的收获**（关于社会调查研究方法的深层认知）\n"
        "用中文输出，Markdown格式，语气亲和但保持学术性。"
    )
    messages = [
        {"role": "system", "content": "你是一位社会调查方法论导师，擅长从研究实践中提炼经验教训，帮助研究者持续成长。"},
        {"role": "user", "content": prompt},
    ]
    lessons = await ai.chat(messages, temperature=0.7, max_tokens=3072, task="lessons")
    return {"project_id": project_id, "lessons": lessons}


@router.delete("/{project_id}")
async def delete_project(
    project_id: int,
    profile: UserProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
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
    await db.delete(project)
    await db.commit()
    return {"deleted": project_id}
