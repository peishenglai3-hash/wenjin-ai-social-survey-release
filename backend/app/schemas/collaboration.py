"""Typed request schemas for the collaboration V1 membership boundary."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


CollaborationRole = Literal["editor", "reviewer", "viewer"]


class InvitationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invitee_profile_id: int = Field(gt=0)
    role: CollaborationRole = "viewer"


class MemberRoleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: CollaborationRole

