"""Memory & Skills management API — CRUD for user memories and saved skills.

Endpoints:
  GET  /memory/list     — list saved memories for current profile
  POST /memory/delete   — delete a single memory
  GET  /skills/list     — list saved skills for current profile
  POST /skills/save     — manually save a skill (prompt template)
  POST /skills/delete   — delete a single skill
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_ai_service, get_db
from app.api.deps_auth import require_user, get_current_profile
from app.models.user import UserAccount
from app.models.survey import UserProfile
from app.services.ai import AIService
from app.services.memory_service import MemoryService
from app.services.skill_safety import render_skill_prompt

router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("/list")
async def list_memories(
    user: UserAccount = Depends(require_user),
    profile: UserProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    """List all saved memories for a user profile (read-only — does not bump hit counts)."""
    profile_id = profile.id  # Derived from JWT, not from request
    memories = await MemoryService.list_memories(db, profile_id, limit=50)
    return {
        "memories": [
            {
                "id": m.id,
                "category": m.category,
                "key": m.key,
                "value": m.value,
                "confidence": m.confidence,
                "importance": m.importance,
                "source": m.source,
                "hit_count": m.hit_count,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in memories
        ]
    }


@router.post("/delete")
async def delete_memory(
    payload: dict,
    user: UserAccount = Depends(require_user),
    profile: UserProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    """Delete a single memory by id."""
    memory_id = payload.get("memory_id")
    profile_id = profile.id  # Derived from JWT, not from request
    if not memory_id:
        return {"ok": False, "error": "memory_id is required"}
    ok = await MemoryService.delete_memory(db, int(memory_id), int(profile_id))
    return {"ok": ok}


@router.post("/confirm")
async def confirm_memory(
    payload: dict,
    user: UserAccount = Depends(require_user),
    profile: UserProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    """User confirms a memory — boost confidence."""
    memory_id = payload.get("memory_id")
    profile_id = profile.id  # Derived from JWT, not from request
    if not memory_id:
        return {"ok": False, "error": "memory_id is required"}
    ok = await MemoryService.confirm_memory(db, int(memory_id), int(profile_id))
    return {"ok": ok}


@router.post("/edit")
async def edit_memory(
    payload: dict,
    user: UserAccount = Depends(require_user),
    profile: UserProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    """Edit memory fields (value, key, category). Only non-None fields are updated."""
    memory_id = payload.get("memory_id")
    profile_id = profile.id  # Derived from JWT, not from request
    if not memory_id:
        return {"ok": False, "error": "memory_id is required"}
    ok = await MemoryService.edit_memory(
        db, int(memory_id), int(profile_id),
        value=payload.get("value"),
        key=payload.get("key"),
        category=payload.get("category"),
    )
    return {"ok": ok}


@router.post("/suppress")
async def suppress_memory(
    payload: dict,
    user: UserAccount = Depends(require_user),
    profile: UserProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    """Suppress a memory — sets confidence to 0.1, retaining key to prevent re-extraction."""
    memory_id = payload.get("memory_id")
    profile_id = profile.id  # Derived from JWT, not from request
    if not memory_id:
        return {"ok": False, "error": "memory_id is required"}
    ok = await MemoryService.suppress_memory(db, int(memory_id), int(profile_id))
    return {"ok": ok}


# ── Skills ────────────────────────────────────────────────────────────────────

router_skills = APIRouter(prefix="/skills", tags=["skills"])


@router_skills.get("/list")
async def list_skills(
    category: str | None = None,
    user: UserAccount = Depends(require_user),
    profile: UserProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    """List saved skills for a user profile, optionally filtered by category."""
    profile_id = profile.id  # Derived from JWT, not from request
    skills = await MemoryService.list_user_skills(db, profile_id, category)
    return {
        "skills": [
            {
                "id": s.id,
                "name": s.name,
                "description": s.description,
                "prompt_template": s.prompt_template,
                "skill_type": s.skill_type,
                "category": s.category,
                "tags": s.tags,
                "usage_count": s.usage_count,
                "is_public": s.is_public,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in skills
        ]
    }


@router_skills.post("/save")
async def save_skill(
    payload: dict,
    user: UserAccount = Depends(require_user),
    profile: UserProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
    ai: AIService = Depends(get_ai_service),
):
    """Manually save a skill (prompt template).

    Expected payload:
      name, description, prompt_template, category, tags
    If prompt_template is empty but user_message + assistant_reply are provided,
    the AI auto-generates the template.
    """
    profile_id = profile.id  # Derived from JWT, not from request

    # Auto-generate from dialogue if no template provided
    if not payload.get("prompt_template") and payload.get("user_message") and payload.get("assistant_reply"):
        skill_data = await MemoryService.generate_skill_from_dialogue(
            ai, payload["user_message"], payload["assistant_reply"],
        )
        if not skill_data:
            return {"ok": False, "error": "Could not auto-generate skill from this dialogue"}
    else:
        skill_data = {
            "name": payload.get("name", "未命名技能"),
            "description": payload.get("description", ""),
            "prompt_template": payload.get("prompt_template", ""),
            "category": payload.get("category", "general"),
            "tags": payload.get("tags", []),
        }

    source = ""
    if payload.get("user_message") and payload.get("assistant_reply"):
        source = f"Q: {payload['user_message'][:250]}\nA: {payload['assistant_reply'][:250]}"

    skill = await MemoryService.save_skill(db, int(profile_id), skill_data, source)
    if skill:
        return {"ok": True, "skill": {"id": skill.id, "name": skill.name}}
    return {"ok": False, "error": "Database error"}


@router_skills.post("/delete")
async def delete_skill(
    payload: dict,
    user: UserAccount = Depends(require_user),
    profile: UserProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    """Delete a single skill by id."""
    skill_id = payload.get("skill_id")
    profile_id = profile.id  # Derived from JWT, not from request
    if not skill_id:
        return {"ok": False, "error": "skill_id is required"}
    ok = await MemoryService.delete_skill(db, int(skill_id), int(profile_id))
    return {"ok": ok}


@router_skills.post("/use")
async def use_skill(
    payload: dict,
    user: UserAccount = Depends(require_user),
    profile: UserProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
    ai: AIService = Depends(get_ai_service),
):
    """Execute a saved skill — fill its prompt template and get AI response.

    payload: skill_id, context (dict of template variables to fill)
    """
    skill_id = payload.get("skill_id")
    profile_id = profile.id  # Derived from JWT, not from request
    context = payload.get("context", {})

    if not skill_id:
        return {"ok": False, "error": "skill_id is required"}

    skills = await MemoryService.list_user_skills(db, int(profile_id))
    skill = next((s for s in skills if s.id == int(skill_id)), None)
    if not skill:
        return {"ok": False, "error": "Skill not found"}

    # Fill template placeholders
    prompt = render_skill_prompt(skill.prompt_template, context)

    # Execute
    messages = [
        {"role": "system", "content": f"你正在执行用户保存的技能「{skill.name}」。\n{skill.description}"},
        {"role": "user", "content": prompt},
    ]
    result = await ai.chat(messages, temperature=0.7, max_tokens=4096, task="guidance")

    # Bump usage count
    skill.usage_count = (skill.usage_count or 0) + 1
    await db.commit()

    return {"ok": True, "reply": result, "skill_name": skill.name}
