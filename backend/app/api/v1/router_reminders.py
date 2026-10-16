
"""B.4 ContextualReminders API endpoint — GET /api/v1/reminders"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.deps_auth import require_admin
from app.models.user import UserAccount
from app.services.contextual_reminders import get_reminders
from app.services.knowledge_ingestion import ingest_all

router = APIRouter(prefix="/reminders", tags=["ContextualReminders"])


@router.get("")
async def reminders(
    context: str = Query(..., min_length=3, description="Current interview context text for keyword matching"),
    mode: str = Query("deep_one_on_one", description="Interview mode: deep_one_on_one, focus_group, field_casual, structured_survey"),
    top_n: int = Query(3, ge=1, le=10, description="Max reminders to return"),
    db: AsyncSession = Depends(get_db),
):
    """Get contextual reminders for in-interview AI guidance.
    
    Matches trigger keywords against interview context, retrieves relevant
    knowledge cards, and returns ranked reminder prompts for AI injection.
    """
    results = await get_reminders(db, context_text=context, mode=mode, top_n=top_n)
    return {
        "reminders": results,
        "count": len(results),
        "context": context[:200],
        "mode": mode,
    }


@router.post("/ingest")
async def run_ingestion(
    db: AsyncSession = Depends(get_db),
    _: UserAccount = Depends(require_admin),
):
    """Admin: trigger knowledge card ingestion from JSON files. Idempotent."""
    result = await ingest_all(db)
    return result
