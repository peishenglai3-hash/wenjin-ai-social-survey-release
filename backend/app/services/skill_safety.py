"""Data-only skill boundary shared by private use and public publishing."""

from __future__ import annotations

import re
from collections.abc import Mapping

from fastapi import HTTPException, status


MAX_SKILL_PROMPT_CHARS = 20_000
MAX_SKILL_CONTEXT_KEYS = 32
MAX_SKILL_CONTEXT_VALUE_CHARS = 4_000

_SECRET_PATTERN = re.compile(
    r"(?i)(?:api[_-]?key|secret|password|authorization)\s*[:=]\s*\S+|"
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----|\bsk-[A-Za-z0-9_-]{16,}\b"
)
_EXECUTABLE_MARKER = re.compile(
    r"(?i)__import__\s*\(|subprocess\.|os\.system\s*\(|eval\s*\(|exec\s*\(|<script\b"
)
_CONTEXT_KEY = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")


def validate_public_skill_text(value: str | None, *, field: str, max_chars: int) -> None:
    """Reject oversized, credential-bearing, or executable-looking public data."""
    if value is None:
        return
    if len(value) > max_chars:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{field} exceeds the public skill size limit",
        )
    if _SECRET_PATTERN.search(value):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{field} contains a credential-like value; remove it before publishing",
        )
    if _EXECUTABLE_MARKER.search(value):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{field} contains an executable marker; public skills are data-only",
        )


def validate_public_skill(
    *,
    name: str,
    description: str,
    prompt_template: str,
    readme: str | None,
    example_input: str | None,
    example_output: str | None,
) -> None:
    """Validate all fields that can cross the public marketplace boundary."""
    validate_public_skill_text(name, field="name", max_chars=200)
    validate_public_skill_text(description, field="description", max_chars=20_000)
    validate_public_skill_text(prompt_template, field="prompt_template", max_chars=MAX_SKILL_PROMPT_CHARS)
    validate_public_skill_text(readme, field="readme", max_chars=20_000)
    validate_public_skill_text(example_input, field="example_input", max_chars=20_000)
    validate_public_skill_text(example_output, field="example_output", max_chars=20_000)


def render_skill_prompt(template: str, context: Mapping[str, object]) -> str:
    """Fill literal placeholders only; never evaluate templates as code."""
    if not isinstance(context, Mapping):
        raise HTTPException(status_code=422, detail="Skill context must be an object")
    if len(context) > MAX_SKILL_CONTEXT_KEYS:
        raise HTTPException(status_code=422, detail="Too many skill context fields")
    if not isinstance(template, str) or len(template) > MAX_SKILL_PROMPT_CHARS:
        raise HTTPException(status_code=422, detail="Skill prompt exceeds the size limit")

    rendered = template
    for key, value in context.items():
        if not isinstance(key, str) or not _CONTEXT_KEY.fullmatch(key):
            raise HTTPException(status_code=422, detail="Invalid skill context key")
        if isinstance(value, (dict, list, tuple, set)):
            raise HTTPException(status_code=422, detail="Skill context values must be scalar")
        text = str(value)
        if len(text) > MAX_SKILL_CONTEXT_VALUE_CHARS:
            raise HTTPException(status_code=422, detail="Skill context value is too long")
        rendered = rendered.replace(f"{{{key}}}", text)
        if len(rendered) > MAX_SKILL_PROMPT_CHARS:
            raise HTTPException(status_code=422, detail="Rendered skill prompt exceeds the size limit")
    return rendered
