"""Strict request schemas for the WISE proposal review boundary."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


MemoryCategory = Literal[
    "preference",
    "interest",
    "expertise",
    "habit",
    "goal",
    "constraint",
    "methodology",
    "tool",
    "pitfall",
    "note",
    "reflection",
]


class WISEMemoryCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: MemoryCategory
    key: str = Field(min_length=1, max_length=200, pattern=r"^[a-z][a-z0-9_:-]{0,199}$")
    value: str = Field(min_length=1, max_length=2000)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    importance: int = Field(default=3, ge=1, le=5)


class WISEProposalCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["candidate_memory", "micro_innovation", "research_action"] = "candidate_memory"
    title: str = Field(min_length=1, max_length=200)
    proposal_text: str = Field(min_length=1, max_length=8000)
    candidate_memory: WISEMemoryCandidate | None = None
    evidence_refs: list[str] = Field(default_factory=list, max_length=10)
    applicability: str = Field(default="", max_length=2000)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    counterexamples: str = Field(default="", max_length=2000)
    side_effects: str = Field(default="", max_length=2000)
    project_id: int | None = Field(default=None, ge=1)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="after")
    def require_candidate_for_memory(self) -> "WISEProposalCreate":
        if self.kind == "candidate_memory" and self.candidate_memory is None:
            raise ValueError("candidate_memory is required for candidate_memory proposals")
        if self.kind != "candidate_memory" and self.candidate_memory is not None:
            raise ValueError("candidate_memory is only valid for candidate_memory proposals")
        return self


class WISEProposalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: str = Field(default="", max_length=2000)

