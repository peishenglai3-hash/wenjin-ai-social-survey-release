"""Reflection API — reflective iterative profiling endpoints.

Endpoints:
  GET  /reflection/triggers              — list available reflection trigger types
  POST /reflection/start                 — start a reflection session
  POST /reflection/respond               — answer current question, get next
  POST /reflection/conclude              — conclude session, extract insights
  POST /reflection/quick                 — lightweight one-shot reflection
  GET  /reflection/history/{profile_id}  — get reflection session history
  GET  /reflection/evolution/{profile_id} — get profile evolution timeline
  POST /reflection/apply-pending         — apply pending profile adjustments
"""

import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_ai_service, get_db
from app.api.deps_auth import require_user, get_current_profile
from app.models.user import UserAccount
from app.models.survey import (
    UserProfile, SurveyProject, SurveySession,
    ReflectionSession, IterationInsight,
)
from app.services.ai import AIService
from app.services.reflection_service import ReflectionService
from app.services.profile_iterator import ProfileIterator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reflection", tags=["reflection"])

# ── In-memory session store (reflection sessions are stateful dialogues) ──
_active_sessions: dict[str, dict] = {}


def _get_profile_dict(profile) -> dict:
    """Convert a UserProfile ORM object to a dict for reflection context."""
    return {
        "role": profile.role,
        "experience_level": profile.experience_level,
        "paradigm_preference": profile.paradigm_preference,
        "scenario_preference": profile.scenario_preference,
        "theory_driven": profile.theory_driven,
        "methodological_rigidity": profile.methodological_rigidity,
        "analysis_depth": profile.analysis_depth,
        "structure_preference": profile.structure_preference,
        "participation_level": profile.participation_level,
        "tech_dependency": profile.tech_dependency,
        "writing_style": profile.writing_style,
        "learning_preference": profile.learning_preference,
    }


@router.get("/triggers")
async def list_reflection_triggers():
    """List available reflection trigger types with descriptions."""
    return {"triggers": ReflectionService.list_triggers()}


@router.post("/start")
async def start_reflection(
    payload: dict,
    user: UserAccount = Depends(require_user),
    profile: UserProfile = Depends(get_current_profile),
    ai: AIService = Depends(get_ai_service),
    db: AsyncSession = Depends(get_db),
):
    """Start a reflection session after a fieldwork/analysis/project milestone.

    Expected payload:
      - trigger_type: 'fieldwork_completed' | 'analysis_completed' | 'project_completed'
      - project_id: int (optional)
      - source_session_id: int (optional, the fieldwork session that triggered this)
      - extra_context: str (optional, additional context for the reflection)
    """
    trigger_type = payload.get("trigger_type", "fieldwork_completed")
    profile_id = profile.id
    project_id = payload.get("project_id")
    source_session_id = payload.get("source_session_id")

    # Validate trigger_type early — before DB calls
    valid_triggers = {t["id"] for t in ReflectionService.list_triggers()}
    if trigger_type not in valid_triggers:
        return {"error": f"Unknown trigger type: {trigger_type}",
                "available": sorted(valid_triggers)}

    profile_data = _get_profile_dict(profile)

    # Fetch project if provided
    project_data = None
    if project_id:
        try:
            project_id = int(project_id)
        except (TypeError, ValueError):
            return {"error": "Project not found"}
        row = await db.execute(
            select(SurveyProject).where(
                SurveyProject.id == project_id,
                SurveyProject.profile_id == profile.id,
            )
        )
        proj = row.scalar_one_or_none()
        if proj is None:
            return {"error": "Project not found"}
        project_data = {
            "title": proj.title,
            "research_direction": proj.research_direction,
            "phase": proj.phase,
            "paradigm": proj.paradigm,
        }

    # Fetch source context if provided
    source_context = payload.get("extra_context", "")
    if source_session_id:
        try:
            source_session_id = int(source_session_id)
        except (TypeError, ValueError):
            return {"error": "Survey session not found"}
        row = await db.execute(
            select(SurveySession)
            .join(SurveyProject, SurveyProject.id == SurveySession.project_id)
            .where(
                SurveySession.id == source_session_id,
                SurveyProject.profile_id == profile.id,
            )
        )
        session = row.scalar_one_or_none()
        if session is None:
            return {"error": "Survey session not found"}
        if project_id and session.project_id != project_id:
            return {"error": "Survey session not found"}
        if session.transcript_text:
            source_context += f"\n\n调查会话内容摘要：{session.transcript_text[:500]}"
            if session.summary_text:
                source_context += f"\n\nAI生成的摘要：{session.summary_text[:500]}"

    # Initialize the reflection session
    session_state = await ReflectionService.start_reflection(
        trigger_type=trigger_type,
        ai=ai,
        profile_data=profile_data,
        project_data=project_data,
        source_context=source_context,
    )

    if "error" in session_state:
        return session_state

    # Assign a session ID and store in memory
    session_id = str(uuid.uuid4())[:12]
    session_state["session_id"] = session_id
    session_state["profile_id"] = int(profile_id)
    session_state["project_id"] = project_id
    session_state["source_session_id"] = source_session_id
    _active_sessions[session_id] = session_state

    # Persist the reflection session to DB
    try:
        db_session = ReflectionSession(
            profile_id=int(profile_id),
            trigger_type=trigger_type,
            source_session_id=source_session_id,
            source_project_id=int(project_id) if project_id else None,
            status="in_progress",
            questions_json=json.dumps(session_state.get("questions", []), ensure_ascii=False),
        )
        db.add(db_session)
        await db.commit()
        await db.refresh(db_session)
        session_state["db_id"] = db_session.id
    except Exception as e:
        logger.warning("Failed to persist reflection session: %s", e)
        # Non-fatal — in-memory state still works

    return {
        "session_id": session_id,
        "title": session_state.get("title", ""),
        "intro": session_state.get("intro", ""),
        "current_question": session_state["questions"][0] if session_state.get("questions") else None,
        "total_questions": len(session_state.get("questions", [])),
        "question_number": 1,
    }


@router.post("/respond")
async def respond_to_reflection(
    payload: dict,
    profile: UserProfile = Depends(get_current_profile),
    ai: AIService = Depends(get_ai_service),
):
    """Answer the current reflection question and receive the next one
    (or completion signal).

    Expected payload:
      - session_id: str
      - answer: str (user's reflection answer)
    """
    session_id = payload.get("session_id", "")
    answer = payload.get("answer", "").strip()

    if not session_id or session_id not in _active_sessions:
        return {"error": "Session not found or expired. Please start a new reflection."}

    if not answer:
        return {"error": "answer is required"}

    session_state = _active_sessions[session_id]
    if session_state.get("profile_id") != profile.id:
        return {"error": "Session not found or expired. Please start a new reflection."}

    updated = await ReflectionService.process_answer(
        session_state=session_state,
        user_answer=answer,
        ai=ai,
        profile_data=None,  # already in session_state
    )

    _active_sessions[session_id] = updated

    if updated.get("completed"):
        return {
            "completed": True,
            "ai_followup": updated.get("ai_followup", ""),
            "next_step": "conclude",  # hint to call /reflection/conclude
            "total_answered": len(updated.get("answers", [])),
        }

    current_idx = updated.get("current_question_index", 0)
    return {
        "completed": False,
        "ai_followup": updated.get("ai_followup", ""),
        "next_question": updated.get("next_question"),
        "question_number": current_idx + 1,
        "total_questions": len(updated.get("questions", [])),
    }


@router.post("/conclude")
async def conclude_reflection(
    payload: dict,
    profile: UserProfile = Depends(get_current_profile),
    ai: AIService = Depends(get_ai_service),
    db: AsyncSession = Depends(get_db),
):
    """Conclude a reflection session: generate summary, extract insights,
    store to memory, and compute profile adjustments.

    Expected payload:
      - session_id: str
      - apply_adjustments: bool (default false — user must opt in)
    """
    session_id = payload.get("session_id", "")
    apply_adjustments = payload.get("apply_adjustments", False)

    if not session_id or session_id not in _active_sessions:
        return {"error": "Session not found or expired."}

    session_state = _active_sessions[session_id]
    profile_id = session_state.get("profile_id", 0)
    if profile_id != profile.id:
        return {"error": "Session not found or expired."}

    # Fetch profile for spectrum context
    profile_data = None
    if profile_id:
        row = await db.execute(select(UserProfile).where(UserProfile.id == profile_id))
        stored_profile = row.scalar_one_or_none()
        if stored_profile:
            profile_data = _get_profile_dict(stored_profile)

    conclusion = await ReflectionService.conclude_reflection(
        session_state=session_state,
        ai=ai,
        profile_data=profile_data,
    )

    if "error" in conclusion:
        return conclusion

    # Store reflection memories
    memory_count = 0
    if profile_id:
        memory_count = await ReflectionService.store_reflection_memories(
            conclusion=conclusion,
            ai=ai,
            db=db,
            profile_id=profile_id,
            trigger_type=session_state.get("trigger_type", ""),
        )

    # Record iteration insights to DB
    insight_count = 0
    if profile_id and conclusion.get("insights"):
        await ProfileIterator.record_insights(
            db=db,
            profile_id=profile_id,
            insights=conclusion["insights"],
            source_reflection_id=session_state.get("db_id"),
            source_project_id=session_state.get("project_id"),
        )
        insight_count = len(conclusion["insights"])

    # Apply adjustments if user opted in
    applied_adjustments = []
    if apply_adjustments and profile_id:
        result = await ProfileIterator.apply_pending(db, profile_id)
        applied_adjustments = result.get("applied", [])

    # Update DB reflection session
    db_id = session_state.get("db_id")
    if db_id:
        row = await db.execute(
            select(ReflectionSession).where(ReflectionSession.id == db_id)
        )
        db_session = row.scalar_one_or_none()
        if db_session:
            db_session.status = "completed"
            db_session.answers_json = json.dumps(
                session_state.get("answers", []), ensure_ascii=False,
            )
            db_session.summary = conclusion.get("summary", "")
            db_session.insights_json = json.dumps(
                conclusion.get("insights", []), ensure_ascii=False,
            )
            db_session.spectrum_shifts_json = json.dumps(
                conclusion.get("spectrum_shifts", []), ensure_ascii=False,
            )
            await db.commit()

    # Clean up in-memory session
    del _active_sessions[session_id]

    return {
        "summary": conclusion["summary"],
        "insights": conclusion["insights"],
        "spectrum_shifts": conclusion["spectrum_shifts"],
        "memory_count": memory_count,
        "insight_count": insight_count,
        "applied_adjustments": applied_adjustments,
        "total_questions": conclusion.get("total_questions", 0),
    }


@router.post("/quick")
async def quick_reflection(
    payload: dict,
    profile: UserProfile = Depends(get_current_profile),
    ai: AIService = Depends(get_ai_service),
):
    """Generate a lightweight one-shot reflection without full dialogue.

    Expected payload:
      - notes: str (user's field notes or observations)
      - context: str (optional, session background)
    """
    notes = payload.get("notes", "").strip()
    context = payload.get("context", "")

    if not notes:
        return {"error": "notes is required"}

    result = await ReflectionService.quick_reflection(
        ai=ai,
        user_notes=notes,
        session_context=context,
    )
    return {"reflection": result}


@router.get("/history/{profile_id}")
async def get_reflection_history(
    profile_id: int,
    limit: int = 20,
    user: UserAccount = Depends(require_user),
    profile: UserProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    """Get the reflection session history for a profile."""
    if profile.id != profile_id:
        raise HTTPException(status_code=403, detail="Access denied")

    result = await db.execute(
        select(ReflectionSession)
        .where(ReflectionSession.profile_id == profile_id)
        .order_by(ReflectionSession.created_at.desc())
        .limit(limit)
    )
    sessions = result.scalars().all()

    return {
        "profile_id": profile_id,
        "total": len(sessions),
        "sessions": [
            {
                "id": s.id,
                "trigger_type": s.trigger_type,
                "status": s.status,
                "summary": s.summary,
                "insight_count": len(json.loads(s.insights_json or "[]")),
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in sessions
        ],
    }


@router.get("/evolution/{profile_id}")
async def get_profile_evolution(
    profile_id: int,
    dimension: str | None = None,
    user: UserAccount = Depends(require_user),
    profile: UserProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    """Get the profile evolution timeline.

    Query params:
      - dimension: filter to a specific spectrum dimension (optional)
    """
    if profile.id != profile_id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Validate dimension if provided
    valid_dims = [
        "theory_driven", "methodological_rigidity", "analysis_depth",
        "structure_preference", "participation_level", "tech_dependency",
        "writing_style", "learning_preference",
    ]
    if dimension and dimension not in valid_dims:
        return {"error": f"Invalid dimension. Must be one of: {valid_dims}"}

    history = await ProfileIterator.get_evolution_history(
        db, profile_id, dimension=dimension,
    )
    summary = await ProfileIterator.get_evolution_summary(db, profile_id)

    # Get current spectrum values
    row = await db.execute(select(UserProfile).where(UserProfile.id == profile_id))
    profile = row.scalar_one_or_none()

    current_spectrum = {}
    if profile:
        for dim in valid_dims:
            current_spectrum[dim] = getattr(profile, dim, 3)

    return {
        "profile_id": profile_id,
        "current_spectrum": current_spectrum,
        "evolution_summary": summary,
        "history": history,
    }


@router.post("/apply-pending")
async def apply_pending_adjustments(
    payload: dict,
    user: UserAccount = Depends(require_user),
    profile: UserProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger application of pending profile adjustments.

    Expected payload:
      - stability: float (optional, default 0.7, range 0.0-1.0)
    """
    profile_id = profile.id
    stability = payload.get("stability", 0.7)

    if not 0.0 <= stability <= 1.0:
        return {"error": "stability must be between 0.0 and 1.0"}

    result = await ProfileIterator.apply_pending(db, profile_id, stability=stability)
    return result
