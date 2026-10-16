"""Coding endpoints — codebook CRUD, AI coding suggestions, inter-coder reliability."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_ai_service, get_db
from app.api.deps_auth import get_current_profile
from app.models.survey import (
    CodebookCode,
    CodingAssignment,
    SurveyProject,
    SurveySession,
    UserProfile,
)
from app.services.ai import AIService
from app.services.codebook_service import (
    create_code, list_codes, update_code, delete_code,
    suggest_codes, assign_code, list_assignments, delete_assignment,
    calculate_intercoder_reliability, export_codebook, create_version_snapshot,
)

router = APIRouter(prefix="/coding", tags=["coding"])


def _coerce_id(value: object) -> int | None:
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


async def _owned_project(
    db: AsyncSession, project_id: int, profile_id: int,
) -> SurveyProject | None:
    result = await db.execute(
        select(SurveyProject).where(
            SurveyProject.id == project_id,
            SurveyProject.profile_id == profile_id,
        )
    )
    return result.scalar_one_or_none()


async def _owned_code(
    db: AsyncSession, code_id: int, profile_id: int,
) -> CodebookCode | None:
    result = await db.execute(
        select(CodebookCode)
        .join(SurveyProject, SurveyProject.id == CodebookCode.project_id)
        .where(
            CodebookCode.id == code_id,
            SurveyProject.profile_id == profile_id,
        )
    )
    return result.scalar_one_or_none()


async def _owned_session(
    db: AsyncSession, session_id: int, profile_id: int,
) -> SurveySession | None:
    result = await db.execute(
        select(SurveySession)
        .join(SurveyProject, SurveyProject.id == SurveySession.project_id)
        .where(
            SurveySession.id == session_id,
            SurveyProject.profile_id == profile_id,
        )
    )
    return result.scalar_one_or_none()


async def _owned_assignment(
    db: AsyncSession, assignment_id: int, profile_id: int,
) -> CodingAssignment | None:
    result = await db.execute(
        select(CodingAssignment)
        .join(SurveySession, SurveySession.id == CodingAssignment.session_id)
        .join(SurveyProject, SurveyProject.id == SurveySession.project_id)
        .join(CodebookCode, CodebookCode.id == CodingAssignment.code_id)
        .where(
            CodingAssignment.id == assignment_id,
            SurveyProject.profile_id == profile_id,
            CodebookCode.project_id == SurveyProject.id,
        )
    )
    return result.scalar_one_or_none()


async def _parent_belongs_to_project(
    db: AsyncSession, parent_code_id: int | None, project_id: int,
) -> bool:
    if parent_code_id is None:
        return True
    result = await db.execute(
        select(CodebookCode.id).where(
            CodebookCode.id == parent_code_id,
            CodebookCode.project_id == project_id,
        )
    )
    return result.scalar_one_or_none() is not None


@router.get("/codebooks/{project_id}")
async def get_codebook(
    project_id: int,
    paradigm: str | None = Query(None),
    profile: UserProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    if await _owned_project(db, project_id, profile.id) is None:
        return {"error": "Project not found"}
    codes = await list_codes(db, project_id, paradigm=paradigm)
    return {
        "codes": [
            {"id": c.id, "name": c.name, "definition": c.definition,
             "example": c.example, "exclusion_criteria": c.exclusion_criteria,
             "parent_code_id": c.parent_code_id, "paradigm": c.paradigm,
             "color": c.color, "sort_order": c.sort_order, "version": c.version,
             "created_at": str(c.created_at) if c.created_at else None}
            for c in codes
        ], "total": len(codes),
    }


@router.post("/codebooks/{project_id}/codes")
async def add_code(
    project_id: int,
    payload: dict,
    profile: UserProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    if await _owned_project(db, project_id, profile.id) is None:
        return {"error": "Project not found"}
    parent_code_id = payload.get("parent_code_id")
    if parent_code_id is not None and not await _parent_belongs_to_project(db, parent_code_id, project_id):
        return {"error": "Parent code not found"}
    code = await create_code(
        db, project_id, name=payload.get("name", ""),
        definition=payload.get("definition", ""),
        example=payload.get("example", ""),
        exclusion_criteria=payload.get("exclusion_criteria", ""),
        parent_code_id=parent_code_id,
        paradigm=payload.get("paradigm", "thematic_analysis"),
        color=payload.get("color", ""),
        created_by_profile_id=profile.id,
    )
    return {"id": code.id, "name": code.name, "paradigm": code.paradigm}


@router.patch("/codebooks/codes/{code_id}")
async def edit_code(
    code_id: int,
    payload: dict,
    profile: UserProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    code = await _owned_code(db, code_id, profile.id)
    if code is None:
        return {"error": "Code not found"}
    parent_code_id = _coerce_id(payload.get("parent_code_id")) if "parent_code_id" in payload else None
    if "parent_code_id" in payload and parent_code_id == code_id:
        return {"error": "A code cannot be its own parent"}
    if "parent_code_id" in payload and not await _parent_belongs_to_project(
        db, parent_code_id, code.project_id
    ):
        return {"error": "Parent code not found"}
    editable_fields = {
        key: payload[key]
        for key in (
            "name", "definition", "example", "exclusion_criteria",
            "parent_code_id", "paradigm", "color", "sort_order",
        )
        if key in payload
    }
    if "parent_code_id" in payload:
        editable_fields["parent_code_id"] = parent_code_id
    code = await update_code(db, code_id, **editable_fields)
    if code is None:
        return {"error": "Code not found"}
    return {"id": code.id, "name": code.name, "definition": code.definition}


@router.delete("/codebooks/codes/{code_id}")
async def remove_code(
    code_id: int,
    profile: UserProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    if await _owned_code(db, code_id, profile.id) is None:
        return {"error": "Code not found"}
    ok = await delete_code(db, code_id)
    if not ok:
        return {"error": "Code not found"}
    return {"deleted": True, "id": code_id}


@router.post("/suggest")
async def ai_suggest_codes(
    payload: dict,
    profile: UserProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
    ai: AIService = Depends(get_ai_service),
):
    transcript = payload.get("transcript", "")
    research_question = payload.get("research_question", "")
    project_id = payload.get("project_id", 0)
    coding_paradigm = payload.get("coding_paradigm", "auto")
    project_id = _coerce_id(project_id) or 0
    if project_id and await _owned_project(db, project_id, profile.id) is None:
        return {"error": "Project not found"}
    suggestions = await suggest_codes(db, ai, transcript, research_question, project_id, coding_paradigm)
    return {"suggestions": suggestions, "count": len(suggestions)}


@router.post("/assign")
async def create_assignment(
    payload: dict,
    profile: UserProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    code_id = payload.get("code_id", 0)
    session_id = payload.get("session_id", 0)
    code = await _owned_code(db, code_id, profile.id)
    session = await _owned_session(db, session_id, profile.id)
    if code is None or session is None or code.project_id != session.project_id:
        return {"error": "Code or session not found"}
    a = await assign_code(
        db, code_id=code.id, session_id=session.id,
        span_start=payload.get("span_start", 0), span_end=payload.get("span_end", 0),
        quote_text=payload.get("quote_text", ""),
        coder_profile_id=profile.id,
        is_ai_suggested=payload.get("is_ai_suggested", False),
        confidence=payload.get("confidence", 0.5),
    )
    return {"id": a.id, "code_id": a.code_id, "session_id": a.session_id}


@router.get("/assignments/{session_id}")
async def get_assignments(
    session_id: int,
    profile: UserProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    if await _owned_session(db, session_id, profile.id) is None:
        return {"error": "Session not found"}
    assignments = await list_assignments(db, session_id)
    return {
        "assignments": [
            {"id": a.id, "code_id": a.code_id, "session_id": a.session_id,
             "span_start": a.span_start, "span_end": a.span_end,
             "quote_text": a.quote_text, "coder_profile_id": a.coder_profile_id,
             "is_ai_suggested": a.is_ai_suggested, "confidence": a.confidence}
            for a in assignments
        ], "total": len(assignments),
    }


@router.delete("/assignments/{assignment_id}")
async def remove_assignment(
    assignment_id: int,
    profile: UserProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    if await _owned_assignment(db, assignment_id, profile.id) is None:
        return {"error": "Assignment not found"}
    ok = await delete_assignment(db, assignment_id)
    if not ok:
        return {"error": "Assignment not found"}
    return {"deleted": True, "id": assignment_id}


@router.get("/reliability/{session_id}")
async def get_reliability(
    session_id: int,
    profile: UserProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    if await _owned_session(db, session_id, profile.id) is None:
        return {"error": "Session not found"}
    return await calculate_intercoder_reliability(db, session_id)


@router.get("/export/{project_id}")
async def export_codebook_endpoint(
    project_id: int,
    fmt: str = Query("markdown"),
    profile: UserProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    from fastapi.responses import PlainTextResponse
    if await _owned_project(db, project_id, profile.id) is None:
        return {"error": "Project not found"}
    result = await export_codebook(db, project_id, fmt=fmt)
    media = "application/json" if fmt == "json" else "text/markdown; charset=utf-8"
    return PlainTextResponse(content=result, media_type=media)


@router.post("/versions/{project_id}")
async def snapshot_codebook(
    project_id: int,
    payload: dict,
    profile: UserProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    if await _owned_project(db, project_id, profile.id) is None:
        return {"error": "Project not found"}
    version = await create_version_snapshot(
        db, project_id,
        created_by_profile_id=profile.id,
        changelog=payload.get("changelog", ""),
    )
    return {"id": version.id, "version_number": version.version_number, "changelog": version.changelog}
