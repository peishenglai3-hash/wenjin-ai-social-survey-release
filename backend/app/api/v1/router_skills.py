"""Skill system endpoints — list and execute registered AI skills."""

from fastapi import APIRouter, Depends

from app.api.deps import get_ai_service
from app.services.ai import AIService
from app.services.skill_safety import validate_skill_payload
from app.skills.registry import skill_registry

router = APIRouter(tags=["skills"])


@router.get("/skills")
async def list_skills():
    return {"skills": skill_registry.list_skills()}


@router.post("/skills/{skill_name}")
async def execute_skill(skill_name: str, payload: dict, ai: AIService = Depends(get_ai_service)):
    validate_skill_payload(payload)
    skill = skill_registry.get(skill_name)
    if not skill:
        return {"error": f"Unknown skill: {skill_name}"}
    result = await skill.execute(ai, payload)
    return {"skill": skill_name, "result": result.content}
