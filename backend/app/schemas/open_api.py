"""Public request/response schemas for the versioned Open API gateway."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


MAX_TOTAL_INPUT_CHARS = 200_000


class OpenAPIMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1, max_length=100_000)


class OpenAPIChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    messages: list[OpenAPIMessage] = Field(min_length=1, max_length=64)
    provider: str | None = Field(default=None, min_length=1, max_length=64)
    model: str | None = Field(default=None, min_length=1, max_length=128)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1024, ge=1, le=8192)
    project_id: int | None = Field(default=None, ge=1)

    @field_validator("messages")
    @classmethod
    def messages_must_not_be_blank(cls, value: list[OpenAPIMessage]) -> list[OpenAPIMessage]:
        if not any(message.role == "user" for message in value):
            raise ValueError("at least one user message is required")
        return value

    @model_validator(mode="after")
    def input_size_must_be_bounded(self) -> "OpenAPIChatRequest":
        total_chars = sum(len(message.content) for message in self.messages)
        if total_chars > MAX_TOTAL_INPUT_CHARS:
            raise ValueError(
                f"combined message content cannot exceed {MAX_TOTAL_INPUT_CHARS} characters"
            )
        return self


class OpenAPIUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class OpenAPIChatResponse(BaseModel):
    id: str
    object: Literal["chat.completion"] = "chat.completion"
    request_id: str | None = None
    provider: str
    model: str
    content: str
    usage: OpenAPIUsage
    quota_remaining_tokens: int | None = None

