"""Knowledge Card system — cross-project insight extraction, storage, and push.

Knowledge Cards distill reusable methodology insights from completed
survey projects. They are tagged, categorized, and ranked so the system can
push relevant cards when the user starts new projects.
"""

import json
import logging

from fastapi import APIRouter, Depends, Query
from app.api.deps_auth import require_user, get_current_profile
from app.models.user import UserAccount

logger = logging.getLogger(__name__)
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_ai_service, get_db
from app.models.survey import (
    AnalysisResult,
    ExportDocument,
    KnowledgeCard,
    SurveyProject,
    SurveySession,
    UserProfile,
)
from app.services.ai import AIService

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

CATEGORIES = {
    "methodology": {"label": "方法论", "icon": "📐", "desc": "关于研究方法的经验总结"},
    "pitfall": {"label": "避坑指南", "icon": "⚠️", "desc": "实际操作中的常见错误与预防"},
    "tool": {"label": "工具技巧", "icon": "🛠", "desc": "软硬件工具的使用心得"},
    "ethics": {"label": "伦理提醒", "icon": "⚖️", "desc": "调查伦理相关的注意事项"},
    "theory": {"label": "理论洞察", "icon": "💡", "desc": "从实践中获得的理论启发"},
    "workflow": {"label": "流程优化", "icon": "🔄", "desc": "工作流程改进经验"},
}


# ── Category metadata ─────────────────────────────────────────────

@router.get("/categories")
async def list_categories():
    return {"categories": [{"id": k, **v} for k, v in CATEGORIES.items()]}


# ── CRUD ───────────────────────────────────────────────────────────

@router.get("/cards")
async def list_cards(
    profile: UserProfile = Depends(get_current_profile),
    category: str = Query(""),
    paradigm: str = Query(""),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List knowledge cards, optionally filtered by category and paradigm."""
    q = select(KnowledgeCard).where(KnowledgeCard.profile_id == profile.id)
    if category:
        q = q.where(KnowledgeCard.category == category)
    if paradigm:
        q = q.where(KnowledgeCard.paradigm == paradigm)
    q = q.order_by(
        KnowledgeCard.importance.desc(),
        KnowledgeCard.reuse_count.desc(),
        KnowledgeCard.created_at.desc(),
    ).limit(limit)

    result = await db.execute(q)
    cards = result.scalars().all()
    return {
        "cards": [
            {
                "id": c.id, "title": c.title, "category": c.category,
                "content": c.content,
                "tags": json.loads(c.tags) if c.tags else [],
                "paradigm": c.paradigm, "phase": c.phase, "theme": c.theme,
                "importance": c.importance, "reuse_count": c.reuse_count,
                "source_project_id": c.source_project_id,
                "created_at": str(c.created_at) if c.created_at else None,
            }
            for c in cards
        ],
        "total": len(cards),
    }


@router.get("/cards/relevant")
async def get_relevant_cards(
    profile: UserProfile = Depends(get_current_profile),
    paradigm: str = Query("qualitative"),
    phase: str = Query(""),
    topic: str = Query(""),
    limit: int = Query(5, le=20),
    db: AsyncSession = Depends(get_db),
):
    """Get knowledge cards most relevant to current context."""
    q = select(KnowledgeCard).where(KnowledgeCard.profile_id == profile.id)
    q = q.where(
        (KnowledgeCard.paradigm == paradigm) | (KnowledgeCard.paradigm == "mixed")
    )
    if phase:
        q = q.where(KnowledgeCard.phase == phase)

    q = q.order_by(
        KnowledgeCard.importance.desc(),
        KnowledgeCard.reuse_count.desc(),
    ).limit(limit * 2)

    result = await db.execute(q)
    cards = result.scalars().all()

    scored = []
    for c in cards:
        score = c.importance * 2 + c.reuse_count
        if topic:
            title_low = c.title.lower()
            content_low = (c.content or "").lower()[:200]
            tags_low = (c.tags or "").lower()
            topic_low = topic.lower()
            for kw in topic_low.split():
                if kw in title_low:
                    score += 5
                if kw in content_low:
                    score += 2
                if kw in tags_low:
                    score += 3
        scored.append((score, c))

    scored.sort(key=lambda x: x[0], reverse=True)
    return {
        "cards": [
            {
                "id": c.id, "title": c.title, "category": c.category,
                "content": c.content,
                "tags": json.loads(c.tags) if c.tags else [],
                "paradigm": c.paradigm, "phase": c.phase,
                "importance": c.importance, "reuse_count": c.reuse_count,
                "relevance_score": score,
            }
            for score, c in scored[:limit]
        ],
    }


@router.get("/cards/{card_id}")
async def get_card(
    card_id: int,
    profile: UserProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(KnowledgeCard).where(
            KnowledgeCard.id == card_id,
            KnowledgeCard.profile_id == profile.id,
        )
    )
    card = result.scalar_one_or_none()
    if not card:
        return {"error": "Card not found"}
    return {
        "id": card.id, "title": card.title, "category": card.category,
        "content": card.content,
        "tags": json.loads(card.tags) if card.tags else [],
        "paradigm": card.paradigm, "phase": card.phase, "theme": card.theme,
        "importance": card.importance, "reuse_count": card.reuse_count,
        "source_project_id": card.source_project_id,
        "created_at": str(card.created_at) if card.created_at else None,
    }


@router.post("/cards/{card_id}/reuse")
async def mark_card_reuse(
    card_id: int,
    profile: UserProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(KnowledgeCard).where(
            KnowledgeCard.id == card_id,
            KnowledgeCard.profile_id == profile.id,
        )
    )
    card = result.scalar_one_or_none()
    if not card:
        return {"error": "Card not found"}
    card.reuse_count += 1
    await db.commit()
    return {"id": card.id, "reuse_count": card.reuse_count}


@router.delete("/cards/{card_id}")
async def delete_card(
    card_id: int,
    profile: UserProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(KnowledgeCard).where(
            KnowledgeCard.id == card_id,
            KnowledgeCard.profile_id == profile.id,
        )
    )
    card = result.scalar_one_or_none()
    if not card:
        return {"error": "Card not found"}
    await db.delete(card)
    await db.commit()
    return {"deleted": card_id}


# ── AI Extraction ───────────────────────────────────────────────────

@router.post("/extract")
async def extract_knowledge_cards(
    payload: dict,
    profile: UserProfile = Depends(get_current_profile),
    ai: AIService = Depends(get_ai_service),
    db: AsyncSession = Depends(get_db),
):
    """AI extracts reusable knowledge cards from completed projects."""
    project_id = payload.get("project_id")
    theme = payload.get("theme", "academic")

    if project_id:
        result = await db.execute(
            select(SurveyProject).where(
                SurveyProject.id == project_id,
                SurveyProject.profile_id == profile.id,
            )
        )
        projects = result.scalars().all()
    else:
        result = await db.execute(
            select(SurveyProject).where(
                SurveyProject.profile_id == profile.id,
                SurveyProject.status.in_(["completed", "active"]),
            )
        )
        projects = result.scalars().all()

    if not projects:
        return {"error": "No completed projects found", "cards_created": 0}

    all_created = []

    for project in projects:
        context_parts = [f"项目: {project.title}"]
        if project.research_direction:
            context_parts.append(f"方向: {project.research_direction}")
        if project.topic_argumentation:
            context_parts.append(f"选题论证摘要: {project.topic_argumentation[:600]}")
        if project.methodology_guidance:
            context_parts.append(f"方法论指导摘要: {project.methodology_guidance[:600]}")

        sess_result = await db.execute(
            select(SurveySession).where(SurveySession.project_id == project.id)
        )
        sessions = sess_result.scalars().all()
        if sessions:
            context_parts.append(f"田野访谈场次: {len(sessions)}")
            first = sessions[0]
            if first.notes:
                context_parts.append(f"田野笔记示例: {first.notes[:300]}")

        anal_result = await db.execute(
            select(AnalysisResult).where(AnalysisResult.project_id == project.id).limit(1)
        )
        analyses = anal_result.scalars().all()
        if analyses:
            context_parts.append(f"分析摘要: {analyses[0].content[:500]}")

        context = "\n".join(context_parts)

        prompt = (
            f"项目信息:\n{context}\n\n"
            "请从以上项目经验中提取可复用的知识卡片。每张卡片应该是一个具体的、可操作的方法论洞察。\n\n"
            "请生成3-6张卡片，尽量覆盖不同类别。用以下JSON格式输出（直接输出JSON，不要用markdown包裹）：\n"
            '[\n  {\n    "category": "methodology|pitfall|tool|ethics|theory|workflow",\n'
            '    "title": "卡片标题（简洁、具体、可检索，不超过30字）",\n'
            '    "content": "详细内容（包含具体场景、做了什么、效果如何、可迁移建议，100-300字）",\n'
            '    "tags": ["标签1", "标签2", "标签3"],\n'
            '    "paradigm": "qualitative|quantitative|mixed",\n'
            '    "phase": "pre_survey|during_survey|post_survey|completed",\n'
            '    "importance": 1-5的整数（5=通用性强、几乎所有同类项目都能受益）\n'
            '  }\n]\n'
            "要求：每张卡片必须基于项目的具体经验，不是泛泛而谈。"
            "内容要具体到「在什么情况下」「做了什么」「效果如何」「下次怎么做」。"
        )

        messages = [
            {"role": "system", "content": "你是一位社会调查方法论专家，擅长从研究经验中提炼结构化知识。"
             "你输出的知识卡片具体、可操作、可检索。"},
            {"role": "user", "content": prompt},
        ]
        try:
            ai_output = await ai.chat(messages, temperature=0.6, max_tokens=4096, task="knowledge_extract")
        except Exception:
            logger.warning("Knowledge extraction AI call failed for project, skipping", exc_info=True)
            continue

        try:
            json_str = ai_output
            if "```json" in ai_output:
                json_str = ai_output.split("```json")[1].split("```")[0]
            elif "```" in ai_output:
                json_str = ai_output.split("```")[1].split("```")[0]
            cards_data = json.loads(json_str.strip())
        except (json.JSONDecodeError, IndexError):
            continue

        for cd in cards_data:
            card = KnowledgeCard(
                profile_id=profile.id,
                source_project_id=project.id,
                category=cd.get("category", "methodology"),
                title=cd.get("title", "")[:200],
                content=cd.get("content", "")[:2000],
                tags=json.dumps(cd.get("tags", []), ensure_ascii=False),
                paradigm=cd.get("paradigm", project.paradigm),
                phase=cd.get("phase", project.phase),
                theme=theme,
                importance=min(5, max(1, cd.get("importance", 3))),
            )
            db.add(card)
            all_created.append(card.title)

        await db.commit()

    total_result = await db.execute(
        select(func.count(KnowledgeCard.id)).where(KnowledgeCard.profile_id == profile.id)
    )
    total_cards = total_result.scalar() or 0

    return {
        "cards_created": len(all_created),
        "cards_titles": all_created,
        "projects_scanned": len(projects),
        "total_cards_now": total_cards,
    }


# ── Stats ───────────────────────────────────────────────────────────

@router.get("/stats")
async def knowledge_stats(
    profile: UserProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    total_result = await db.execute(
        select(func.count(KnowledgeCard.id)).where(KnowledgeCard.profile_id == profile.id)
    )
    by_cat_result = await db.execute(
        select(KnowledgeCard.category, func.count(KnowledgeCard.id))
        .where(KnowledgeCard.profile_id == profile.id)
        .group_by(KnowledgeCard.category)
    )
    top_result = await db.execute(
        select(KnowledgeCard)
        .where(KnowledgeCard.profile_id == profile.id)
        .order_by(KnowledgeCard.reuse_count.desc())
        .limit(5)
    )

    by_category = {row[0]: row[1] for row in by_cat_result.all()}
    return {
        "total_cards": total_result.scalar() or 0,
        "by_category": {k: {"label": CATEGORIES.get(k, {}).get("label", k), "count": v}
                        for k, v in by_category.items()},
        "top_reused": [
            {"id": c.id, "title": c.title, "category": c.category, "reuse_count": c.reuse_count}
            for c in top_result.scalars().all()
        ],
    }
