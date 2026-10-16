"""WISE proposal lifecycle and the only promotion path into long-term memory."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware.request_context import get_request_id
from app.models.survey import SurveyProject, UserMemory
from app.models.wise import WISEProposal
from app.schemas.wise import WISEProposalCreate
from app.services.memory_service import MemoryService


class WISEService:
    """Create pending proposals and require explicit approval for promotion."""

    @staticmethod
    def _serialize(proposal: WISEProposal) -> dict:
        return {
            "id": proposal.id,
            "profile_id": proposal.profile_id,
            "project_id": proposal.project_id,
            "kind": proposal.kind,
            "status": proposal.status,
            "title": proposal.title,
            "proposal_text": proposal.proposal_text,
            "candidate_memory": json.loads(proposal.candidate_memory_json or "{}"),
            "evidence_refs": json.loads(proposal.evidence_refs_json or "[]"),
            "applicability": proposal.applicability,
            "confidence": proposal.confidence,
            "counterexamples": proposal.counterexamples,
            "side_effects": proposal.side_effects,
            "source": proposal.source,
            "review_note": proposal.review_note,
            "approved_memory_id": proposal.approved_memory_id,
            "approved_at": proposal.approved_at.isoformat() if proposal.approved_at else None,
            "revoked_at": proposal.revoked_at.isoformat() if proposal.revoked_at else None,
            "created_at": proposal.created_at.isoformat() if proposal.created_at else None,
            "updated_at": proposal.updated_at.isoformat() if proposal.updated_at else None,
        }

    @staticmethod
    async def _validate_project(
        db: AsyncSession, profile_id: int, project_id: int | None
    ) -> None:
        if project_id is None:
            return
        result = await db.execute(
            select(SurveyProject).where(
                SurveyProject.id == project_id,
                SurveyProject.profile_id == profile_id,
            )
        )
        if result.scalar_one_or_none() is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    @classmethod
    async def create(
        cls,
        db: AsyncSession,
        profile_id: int,
        payload: WISEProposalCreate,
        *,
        source: str = "user",
        request_id: str | None = None,
    ) -> tuple[WISEProposal, bool]:
        await cls._validate_project(db, profile_id, payload.project_id)
        if payload.idempotency_key:
            existing = await db.execute(
                select(WISEProposal).where(
                    WISEProposal.profile_id == profile_id,
                    WISEProposal.idempotency_key == payload.idempotency_key,
                )
            )
            proposal = existing.scalar_one_or_none()
            if proposal is not None:
                return proposal, False

        proposal = WISEProposal(
            profile_id=profile_id,
            project_id=payload.project_id,
            kind=payload.kind,
            status="pending",
            title=payload.title,
            proposal_text=payload.proposal_text,
            candidate_memory_json=json.dumps(
                payload.candidate_memory.model_dump() if payload.candidate_memory else {},
                ensure_ascii=False,
                sort_keys=True,
            ),
            evidence_refs_json=json.dumps(payload.evidence_refs, ensure_ascii=False),
            applicability=payload.applicability,
            confidence=payload.confidence,
            counterexamples=payload.counterexamples,
            side_effects=payload.side_effects,
            source=source,
            idempotency_key=payload.idempotency_key,
            request_id=request_id or get_request_id(),
        )
        db.add(proposal)
        await db.commit()
        await db.refresh(proposal)
        return proposal, True

    @staticmethod
    async def list_owned(
        db: AsyncSession, profile_id: int, status_filter: str | None = None
    ) -> list[WISEProposal]:
        stmt = select(WISEProposal).where(WISEProposal.profile_id == profile_id)
        if status_filter:
            stmt = stmt.where(WISEProposal.status == status_filter)
        stmt = stmt.order_by(WISEProposal.created_at.desc()).limit(100)
        return list((await db.execute(stmt)).scalars().all())

    @staticmethod
    async def get_owned(
        db: AsyncSession, profile_id: int, proposal_id: int
    ) -> WISEProposal:
        result = await db.execute(
            select(WISEProposal).where(
                WISEProposal.id == proposal_id,
                WISEProposal.profile_id == profile_id,
            )
        )
        proposal = result.scalar_one_or_none()
        if proposal is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found")
        return proposal

    @staticmethod
    async def approve(
        db: AsyncSession,
        proposal: WISEProposal,
        profile_id: int,
        note: str = "",
    ) -> tuple[WISEProposal, int]:
        if proposal.profile_id != profile_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found")
        if proposal.status == "approved":
            return proposal, 0
        if proposal.status != "pending":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Proposal is not pending")

        saved = 0
        if proposal.kind == "candidate_memory":
            candidate = json.loads(proposal.candidate_memory_json or "{}")
            saved = await MemoryService.save_memories(
                db,
                profile_id,
                [candidate],
                source="wise_approved",
                commit=False,
            )
            memory = (
                await db.execute(
                    select(UserMemory).where(
                        UserMemory.profile_id == profile_id,
                        UserMemory.category == candidate.get("category"),
                        UserMemory.key == candidate.get("key"),
                    )
                )
            ).scalar_one_or_none()
            proposal.approved_memory_id = memory.id if memory else None

        proposal.status = "approved"
        proposal.review_note = note
        proposal.approved_by_profile_id = profile_id
        proposal.approved_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await db.commit()
        await db.refresh(proposal)
        return proposal, saved

    @staticmethod
    async def reject(
        db: AsyncSession,
        proposal: WISEProposal,
        profile_id: int,
        note: str = "",
    ) -> WISEProposal:
        if proposal.profile_id != profile_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found")
        if proposal.status != "pending":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Proposal is not pending")
        proposal.status = "rejected"
        proposal.review_note = note
        await db.commit()
        await db.refresh(proposal)
        return proposal

    @staticmethod
    async def revoke(
        db: AsyncSession,
        proposal: WISEProposal,
        profile_id: int,
        note: str = "",
    ) -> WISEProposal:
        if proposal.profile_id != profile_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found")
        if proposal.status not in {"pending", "approved"}:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Proposal cannot be revoked")
        if proposal.status == "approved" and proposal.approved_memory_id:
            memory = (
                await db.execute(
                    select(UserMemory).where(
                        UserMemory.id == proposal.approved_memory_id,
                        UserMemory.profile_id == profile_id,
                    )
                )
            ).scalar_one_or_none()
            if memory is not None:
                memory.confidence = 0.1
        proposal.status = "revoked"
        proposal.review_note = note
        proposal.revoked_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await db.commit()
        await db.refresh(proposal)
        return proposal

    @classmethod
    async def create_memory_proposals(
        cls,
        db: AsyncSession,
        profile_id: int,
        memories: list[dict],
        *,
        source: str,
        project_id: int | None = None,
    ) -> int:
        """Convert model-extracted memories into pending WISE proposals."""
        count = 0
        for memory in memories[:5]:
            candidate = WISEProposalCreate(
                kind="candidate_memory",
                title=f"候选记忆：{memory.get('key', '未命名')}",
                proposal_text=memory.get("value", ""),
                candidate_memory=memory,
                evidence_refs=[],
                confidence=float(memory.get("confidence", 0.5)),
                project_id=project_id,
            )
            await cls.create(
                db,
                profile_id,
                candidate,
                source=source,
                request_id=get_request_id(),
            )
            count += 1
        return count
