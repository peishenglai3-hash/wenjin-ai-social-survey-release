"""Researcher Community API — Phase 1: Skill Marketplace MVP.

Endpoints:
  GET    /community/skills          — list published skills (paginated, filterable)
  GET    /community/skills/{id}     — skill detail with author info
  POST   /community/skills/{id}/fork — fork a community skill to my skills
  POST   /community/skills/publish  — publish one of my skills to the community
  GET    /community/skills/search   — full-text search community skills
  GET    /community/skills/categories — category statistics
  GET    /community/researchers     — list researchers with public skills
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.deps_auth import require_user, get_current_profile
from app.models.survey import UserSkill, UserProfile
from app.models.user import UserAccount
from app.schemas.community import CommunitySkillPublish
from app.services.skill_safety import validate_public_skill

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/community", tags=["community"])

# ── Helpers ──────────────────────────────────────────────────────────────────

def _skill_row(s) -> dict:
    """Serialize a UserSkill row to a community-safe dict."""
    return {
        "id": s.id,
        "name": s.name,
        "description": s.description,
        "prompt_template": s.prompt_template,
        "skill_type": s.skill_type,
        "category": s.category,
        "tags": json.loads(s.tags) if isinstance(s.tags, str) else (s.tags or []),
        "usage_count": s.usage_count,
        "is_public": s.is_public,
        "published_at": s.published_at.isoformat() if s.published_at else None,
        "published_version": getattr(s, "published_version", "1.0.0"),
        "fork_count": getattr(s, "fork_count", 0),
        "rating_avg": getattr(s, "rating_avg", 0.0),
        "rating_count": getattr(s, "rating_count", 0),
        "download_count": getattr(s, "download_count", 0),
        "readme": getattr(s, "readme", None),
        "example_input": getattr(s, "example_input", None),
        "example_output": getattr(s, "example_output", None),
        "compatible_models": getattr(s, "compatible_models", "[]"),
        "min_app_version": getattr(s, "min_app_version", "0.2.0"),
        "forked_from_id": getattr(s, "forked_from_id", None),
        "fork_lineage": getattr(s, "fork_lineage", "[]"),
        "execution_mode": "prompt_only",
        "author_id": s.profile_id,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


def _author_row(p) -> dict:
    """Serialize a UserProfile row to a community-safe author summary."""
    return {
        "id": p.id,
        "role": p.role,
        "experience_level": p.experience_level,
        "paradigm_preference": p.paradigm_preference,
        "scenario_preference": p.scenario_preference,
    }


# ── Community Skills ─────────────────────────────────────────────────────────

@router.get("/skills")
async def list_community_skills(
    category: str | None = Query(None, description="Filter by category"),
    skill_type: str | None = Query(None, description="Filter by skill_type"),
    sort: str = Query("latest", description="Sort: latest | popular | rating | forks"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """List published community skills with pagination, filtering, and sorting."""
    base = select(UserSkill).where(UserSkill.is_public == True)

    if category:
        base = base.where(UserSkill.category == category)
    if skill_type:
        base = base.where(UserSkill.skill_type == skill_type)

    # Count
    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    # Sort
    if sort == "popular":
        base = base.order_by(desc(UserSkill.usage_count))
    elif sort == "rating":
        base = base.order_by(desc(text("rating_avg")), desc(text("rating_count")))
    elif sort == "forks":
        base = base.order_by(desc(text("fork_count")))
    else:  # latest
        base = base.order_by(desc(text("COALESCE(published_at, created_at)")))

    offset = (page - 1) * page_size
    rows = (await db.execute(base.offset(offset).limit(page_size))).scalars().all()

    return {
        "skills": [_skill_row(s) for s in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size),
    }


@router.get("/skills/search")
async def search_community_skills(
    q: str = Query(..., min_length=1, description="Search query"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Full-text search across skill name, description, tags, and readme."""
    like = f"%{q}%"
    base = (
        select(UserSkill)
        .where(UserSkill.is_public == True)
        .where(
            or_(
                UserSkill.name.ilike(like),
                UserSkill.description.ilike(like),
                UserSkill.tags.ilike(like),
                text("COALESCE(readme, '')").ilike(like),
            )
        )
    )

    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    offset = (page - 1) * page_size
    rows = (
        (await db.execute(base.order_by(desc(text("COALESCE(published_at, created_at)")))
                          .offset(offset).limit(page_size)))
        .scalars().all()
    )

    return {
        "skills": [_skill_row(s) for s in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "query": q,
    }


@router.get("/skills/categories")
async def community_categories(db: AsyncSession = Depends(get_db)):
    """Return category counts for published skills."""
    rows = (
        await db.execute(
            select(UserSkill.category, func.count(UserSkill.id))
            .where(UserSkill.is_public == True)
            .group_by(UserSkill.category)
        )
    ).all()

    return {
        "categories": [
            {"name": cat, "count": cnt}
            for cat, cnt in rows
        ],
        "total_published": sum(cnt for _, cnt in rows),
    }


@router.get("/skills/{skill_id}")
async def get_community_skill(
    skill_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get a single community skill with author info."""
    skill = await db.get(UserSkill, skill_id)
    if not skill or not skill.is_public:
        return {"error": "Skill not found or not published"}

    author = await db.get(UserProfile, skill.profile_id)
    result = _skill_row(skill)
    result["author"] = _author_row(author) if author else None

    # Get fork lineage if any
    forked_from_id = getattr(skill, "forked_from_id", None)
    if forked_from_id:
        parent = await db.get(UserSkill, forked_from_id)
        if parent:
            result["forked_from"] = {
                "id": parent.id,
                "name": parent.name,
                "author_id": parent.profile_id,
            }

    # Get forks of this skill
    forks_q = (
        select(UserSkill)
        .where(UserSkill.is_public == True)
        .where(UserSkill.forked_from_id == skill_id)
    )
    fork_rows = (await db.execute(forks_q)).scalars().all()
    result["forks"] = [
        {"id": f.id, "name": f.name, "author_id": f.profile_id}
        for f in fork_rows
    ]

    return result


@router.post("/skills/publish")
async def publish_skill(
    payload: CommunitySkillPublish,
    db: AsyncSession = Depends(get_db),
    user: UserAccount = Depends(require_user),
    profile: UserProfile = Depends(get_current_profile),
):
    """Publish one of my existing skills to the community.

    Required: skill_id
    Optional: readme, example_input, example_output, compatible_models
    """
    skill_id = payload.skill_id
    skill = await db.get(UserSkill, skill_id)
    if not skill:
        return {"ok": False, "error": "Skill not found"}
    if skill.profile_id != profile.id:
        return {"ok": False, "error": "You can only publish your own skills"}

    validate_public_skill(
        name=skill.name,
        description=skill.description,
        prompt_template=skill.prompt_template,
        readme=payload.readme if payload.readme is not None else skill.readme,
        example_input=payload.example_input if payload.example_input is not None else skill.example_input,
        example_output=payload.example_output if payload.example_output is not None else skill.example_output,
    )

    # Update community fields
    skill.is_public = True
    skill.published_at = datetime.now(timezone.utc)

    if payload.readme:
        skill.readme = payload.readme
    if payload.example_input:
        skill.example_input = payload.example_input
    if payload.example_output:
        skill.example_output = payload.example_output
    if payload.compatible_models:
        skill.compatible_models = json.dumps(payload.compatible_models)

    await db.commit()
    await db.refresh(skill)

    logger.info(f"User {profile.id} published skill {skill_id} ({skill.name})")
    return {"ok": True, "skill": _skill_row(skill)}


@router.post("/skills/{skill_id}/fork")
async def fork_skill(
    skill_id: int,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    user: UserAccount = Depends(require_user),
    profile: UserProfile = Depends(get_current_profile),
):
    """Fork a community skill into my own skill library."""
    original = await db.get(UserSkill, skill_id)
    if not original or not original.is_public:
        return {"ok": False, "error": "Skill not found or not published"}

    # Increment fork count on original
    orig_fork_count = getattr(original, "fork_count", 0) or 0
    original.fork_count = orig_fork_count + 1

    # Build fork lineage
    lineage_raw = getattr(original, "fork_lineage", "[]") or "[]"
    lineage = json.loads(lineage_raw)
    lineage.append(original.id)

    # Create the forked copy
    forked = UserSkill(
        profile_id=profile.id,
        name=f"{original.name} (Fork)",
        description=original.description,
        prompt_template=original.prompt_template,
        skill_type=original.skill_type,
        category=original.category,
        tags=original.tags,
        is_public=False,  # Fork starts private
        forked_from_id=original.id,
        fork_lineage=json.dumps(lineage),
        readme=getattr(original, "readme", None),
        example_input=getattr(original, "example_input", None),
        example_output=getattr(original, "example_output", None),
        compatible_models=getattr(original, "compatible_models", "[]"),
        source_dialogue_snippet=(
            f"Forked from community skill #{original.id}: {original.name}"
        ),
    )
    db.add(forked)
    await db.commit()
    await db.refresh(forked)

    logger.info(f"User {profile.id} forked skill {skill_id} → new skill {forked.id}")
    return {"ok": True, "skill": _skill_row(forked)}


# ── Researchers ──────────────────────────────────────────────────────────────

@router.get("/researchers")
async def list_researchers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """List researchers who have published at least one community skill."""
    # Find distinct profile_ids with published skills
    sub = (
        select(UserSkill.profile_id, func.count(UserSkill.id).label("skill_count"))
        .where(UserSkill.is_public == True)
        .group_by(UserSkill.profile_id)
        .subquery()
    )

    count_q = select(func.count()).select_from(sub)
    total = (await db.execute(count_q)).scalar() or 0

    offset = (page - 1) * page_size
    rows = (await db.execute(
        select(sub.c.profile_id, sub.c.skill_count)
        .order_by(desc(sub.c.skill_count))
        .offset(offset).limit(page_size)
    )).all()

    researchers = []
    for pid, skill_count in rows:
        profile = await db.get(UserProfile, pid)
        if profile:
            researchers.append({
                **_author_row(profile),
                "skill_count": skill_count,
            })

    return {
        "researchers": researchers,
        "total": total,
        "page": page,
        "page_size": page_size,
    }
