"""WISE review endpoints: proposals first, durable memory only after approval."""

from typing import Literal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.deps_auth import get_current_profile
from app.models.survey import UserProfile
from app.schemas.wise import WISEProposalCreate, WISEProposalDecision
from app.services.wise_service import WISEService

router = APIRouter(prefix="/wise", tags=["wise"])


@router.get("/proposals")
async def list_wise_proposals(
    status_filter: Literal["pending", "approved", "rejected", "revoked"] | None = Query(
        default=None, alias="status"
    ),
    profile: UserProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    proposals = await WISEService.list_owned(db, profile.id, status_filter)
    return {"proposals": [WISEService._serialize(proposal) for proposal in proposals]}


@router.post("/proposals", status_code=status.HTTP_201_CREATED)
async def create_wise_proposal(
    payload: WISEProposalCreate,
    profile: UserProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    proposal, created = await WISEService.create(
        db,
        profile.id,
        payload,
        source="user",
    )
    return {
        "created": created,
        "proposal": WISEService._serialize(proposal),
    }


@router.get("/proposals/{proposal_id}")
async def get_wise_proposal(
    proposal_id: int,
    profile: UserProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    proposal = await WISEService.get_owned(db, profile.id, proposal_id)
    return {"proposal": WISEService._serialize(proposal)}


@router.post("/proposals/{proposal_id}/approve")
async def approve_wise_proposal(
    proposal_id: int,
    payload: WISEProposalDecision | None = None,
    profile: UserProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    proposal = await WISEService.get_owned(db, profile.id, proposal_id)
    proposal, saved = await WISEService.approve(
        db, proposal, profile.id, (payload.note if payload else "")
    )
    return {
        "saved_memory_count": saved,
        "proposal": WISEService._serialize(proposal),
    }


@router.post("/proposals/{proposal_id}/reject")
async def reject_wise_proposal(
    proposal_id: int,
    payload: WISEProposalDecision | None = None,
    profile: UserProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    proposal = await WISEService.get_owned(db, profile.id, proposal_id)
    proposal = await WISEService.reject(
        db, proposal, profile.id, (payload.note if payload else "")
    )
    return {"proposal": WISEService._serialize(proposal)}


@router.post("/proposals/{proposal_id}/revoke")
async def revoke_wise_proposal(
    proposal_id: int,
    payload: WISEProposalDecision | None = None,
    profile: UserProfile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    proposal = await WISEService.get_owned(db, profile.id, proposal_id)
    proposal = await WISEService.revoke(
        db, proposal, profile.id, (payload.note if payload else "")
    )
    return {"proposal": WISEService._serialize(proposal)}
