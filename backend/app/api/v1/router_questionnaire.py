"""Questionnaire endpoints — structured storage, filling, statistics."""
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.deps_auth import get_current_profile
from app.models.survey import (
    Questionnaire,
    QuestionnaireResponse,
    SurveyProject,
    SurveySession,
    UserProfile,
)
from app.schemas.questionnaire import (
    QuestionnaireSave, QuestionnaireOut, ResponseSubmit, ResponseOut,
    QuestionnaireStats, QuestionStat,
)

router = APIRouter(tags=["questionnaire"])


async def _owned_questionnaire(
    db: AsyncSession,
    questionnaire_id: int,
    profile_id: int,
) -> Questionnaire | None:
    result = await db.execute(
        select(Questionnaire)
        .join(SurveyProject, SurveyProject.id == Questionnaire.project_id)
        .where(
            Questionnaire.id == questionnaire_id,
            SurveyProject.profile_id == profile_id,
        )
    )
    return result.scalar_one_or_none()


async def _owned_project(
    db: AsyncSession,
    project_id: int,
    profile_id: int,
) -> SurveyProject | None:
    result = await db.execute(
        select(SurveyProject).where(
            SurveyProject.id == project_id,
            SurveyProject.profile_id == profile_id,
        )
    )
    return result.scalar_one_or_none()


@router.post("/questionnaire/save", response_model=QuestionnaireOut)
async def save_questionnaire(
    body: QuestionnaireSave,
    profile: UserProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    """Save AI-generated questionnaire JSON as structured data."""
    if await _owned_project(db, body.project_id, profile.id) is None:
        raise HTTPException(404, "项目不存在")
    q = Questionnaire(
        project_id=body.project_id,
        title=body.title,
        constructs_json=body.constructs_json,
        questions_json=body.questions_json,
        scales_json=body.scales_json,
        total_items=body.total_items,
        estimated_time_minutes=body.estimated_time_minutes,
        raw_output=body.raw_output,
        paradigm=body.paradigm,
    )
    db.add(q)
    await db.commit()
    await db.refresh(q)
    return q


@router.get("/questionnaire/{id}", response_model=QuestionnaireOut)
async def get_questionnaire(
    id: int,
    profile: UserProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    """Get structured questionnaire by ID."""
    q = await _owned_questionnaire(db, id, profile.id)
    if not q:
        raise HTTPException(404, "问卷不存在")
    return q


@router.get("/questionnaire/by-project/{project_id}", response_model=list[QuestionnaireOut])
async def list_questionnaires(
    project_id: int,
    profile: UserProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    """List all questionnaires for a project."""
    if await _owned_project(db, project_id, profile.id) is None:
        raise HTTPException(404, "项目不存在")
    result = await db.execute(
        select(Questionnaire)
        .where(Questionnaire.project_id == project_id, Questionnaire.is_active == True)
        .order_by(Questionnaire.created_at.desc())
    )
    return result.scalars().all()


@router.post("/questionnaire/{id}/respond", response_model=ResponseOut)
async def submit_response(
    id: int,
    body: ResponseSubmit,
    profile: UserProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    """Submit a filled questionnaire response."""
    q = await _owned_questionnaire(db, id, profile.id)
    if not q:
        raise HTTPException(404, "问卷不存在")

    if body.session_id is not None:
        session_result = await db.execute(
            select(SurveySession)
            .join(SurveyProject, SurveyProject.id == SurveySession.project_id)
            .where(
                SurveySession.id == body.session_id,
                SurveySession.project_id == q.project_id,
                SurveyProject.profile_id == profile.id,
            )
        )
        if session_result.scalar_one_or_none() is None:
            raise HTTPException(404, "调查会话不存在")

    answers_dict = {}
    for a in body.answers:
        answers_dict[a.question_id] = {
            "value": a.value,
            "text": a.question_text,
            "option_index": a.option_index,
            "is_skipped": a.is_skipped,
        }

    resp = QuestionnaireResponse(
        questionnaire_id=id,
        session_id=body.session_id,
        respondent_label=body.respondent_label,
        respondent_metadata_json=body.respondent_metadata_json,
        answers_json=json.dumps(answers_dict, ensure_ascii=False),
        completed=True,
        interview_duration_s=body.interview_duration_s,
    )
    db.add(resp)
    await db.commit()
    await db.refresh(resp)
    return resp


@router.get("/questionnaire/{id}/responses", response_model=list[ResponseOut])
async def list_responses(
    id: int,
    profile: UserProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    """List all responses for a questionnaire."""
    if await _owned_questionnaire(db, id, profile.id) is None:
        raise HTTPException(404, "问卷不存在")
    result = await db.execute(
        select(QuestionnaireResponse)
        .where(QuestionnaireResponse.questionnaire_id == id)
        .order_by(QuestionnaireResponse.created_at.desc())
    )
    return result.scalars().all()


@router.get("/questionnaire/{id}/stats", response_model=QuestionnaireStats)
async def questionnaire_stats(
    id: int,
    profile: UserProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    """Get descriptive statistics for a questionnaire."""
    q = await _owned_questionnaire(db, id, profile.id)
    if not q:
        raise HTTPException(404, "问卷不存在")

    result = await db.execute(
        select(QuestionnaireResponse)
        .where(QuestionnaireResponse.questionnaire_id == id, QuestionnaireResponse.completed == True)
    )
    responses = result.scalars().all()

    try:
        questions = json.loads(q.questions_json)
    except (json.JSONDecodeError, TypeError):
        questions = []

    question_stats: list[QuestionStat] = []
    for q_item in questions:
        qid = q_item.get("id", "")
        qtext = q_item.get("text", "")
        qtype = q_item.get("scale_type", "single_choice")
        freq: dict[str, int] = {}
        skip_count = 0

        for resp in responses:
            try:
                answers = json.loads(resp.answers_json) if isinstance(resp.answers_json, str) else resp.answers_json
            except (json.JSONDecodeError, TypeError):
                answers = {}
            entry = answers.get(qid, {})
            if isinstance(entry, dict):
                if entry.get("is_skipped"):
                    skip_count += 1
                    continue
                val = entry.get("value", "")
            else:
                val = str(entry)
            if val:
                freq[val] = freq.get(val, 0) + 1

        question_stats.append(QuestionStat(
            question_id=qid,
            question_text=qtext,
            scale_type=qtype,
            frequencies=freq,
            skip_count=skip_count,
        ))

    return QuestionnaireStats(
        questionnaire_id=id,
        title=q.title,
        total_responses=len(responses),
        question_stats=question_stats,
    )


@router.delete("/questionnaire/{id}")
async def delete_questionnaire(
    id: int,
    profile: UserProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete a questionnaire."""
    q = await _owned_questionnaire(db, id, profile.id)
    if not q:
        raise HTTPException(404, "问卷不存在")
    q.is_active = False
    await db.commit()
    return {"ok": True}
