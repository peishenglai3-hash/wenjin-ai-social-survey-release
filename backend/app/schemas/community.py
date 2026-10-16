"""Strict schemas for the public, declarative skill marketplace boundary."""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CommunitySkillPublish(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skill_id: int = Field(gt=0)
    readme: str | None = Field(default=None, max_length=20_000)
    example_input: str | None = Field(default=None, max_length=20_000)
    example_output: str | None = Field(default=None, max_length=20_000)
    compatible_models: list[str] | None = Field(default=None, max_length=32)

    @field_validator("compatible_models")
    @classmethod
    def model_names_are_bounded(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        if any(not model.strip() or len(model) > 128 for model in value):
            raise ValueError("compatible model names must be non-empty and at most 128 characters")
        return [model.strip() for model in value]
