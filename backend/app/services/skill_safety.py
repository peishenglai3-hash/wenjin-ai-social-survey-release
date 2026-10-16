"""Data-only skill boundary shared by private use and public publishing."""

from __future__ import annotations

import re
import json
from collections.abc import Mapping
from typing import Any

from fastapi import HTTPException, status


MAX_SKILL_PROMPT_CHARS = 20_000
MAX_SKILL_CONTEXT_KEYS = 32
MAX_SKILL_CONTEXT_VALUE_CHARS = 4_000
MAX_SKILL_PAYLOAD_BYTES = 100_000
MAX_SKILL_PAYLOAD_DEPTH = 8
MAX_SKILL_PAYLOAD_NODES = 512

_SECRET_PATTERN = re.compile(
    r"(?i)(?:api[_-]?key|secret|password|authorization)\s*[:=]\s*\S+|"
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----|\bsk-[A-Za-z0-9_-]{16,}\b"
)
_EXECUTABLE_MARKER = re.compile(
    r"(?i)__import__\s*\(|subprocess\.|os\.system\s*\(|eval\s*\(|exec\s*\(|<script\b"
)
_CONTEXT_KEY = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")
_BLOCKED_PAYLOAD_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "authorization",
        "access_token",
        "refresh_token",
        "client_secret",
        "private_key",
        "base_url",
        "endpoint",
        "shell_command",
        "command",
        "exec",
        "tool_calls",
        "function_call",
    }
)


def validate_skill_payload(payload: Any) -> None:
    """Bound skill execution input before it reaches prompts or providers.

    Built-in skills are prompt/data adapters, not executable plugins.  This
    boundary therefore rejects credential/control-plane fields and limits
    recursive JSON shape without inspecting or storing the research content.
    """
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="Skill payload must be an object")
    try:
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Skill payload must be JSON data") from exc
    if len(encoded.encode("utf-8")) > MAX_SKILL_PAYLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Skill payload exceeds the size limit")

    nodes = 0

    def walk(value: Any, depth: int) -> None:
        nonlocal nodes
        nodes += 1
        if nodes > MAX_SKILL_PAYLOAD_NODES:
            raise HTTPException(status_code=422, detail="Skill payload is too complex")
        if depth > MAX_SKILL_PAYLOAD_DEPTH:
            raise HTTPException(status_code=422, detail="Skill payload nesting is too deep")
        if isinstance(value, dict):
            if len(value) > MAX_SKILL_CONTEXT_KEYS * 2:
                raise HTTPException(status_code=422, detail="Too many skill payload fields")
            for key, child in value.items():
                if not isinstance(key, str):
                    raise HTTPException(status_code=422, detail="Skill payload keys must be strings")
                normalized = key.casefold().replace("-", "_")
                if normalized in _BLOCKED_PAYLOAD_KEYS:
                    raise HTTPException(
                        status_code=422,
                        detail=f"Skill payload field '{key}' is not accepted",
                    )
                walk(child, depth + 1)
        elif isinstance(value, list):
            if len(value) > 128:
                raise HTTPException(status_code=422, detail="Skill payload list is too long")
            for child in value:
                walk(child, depth + 1)
        elif isinstance(value, str):
            if len(value) > MAX_SKILL_PAYLOAD_BYTES:
                raise HTTPException(status_code=413, detail="Skill payload text is too long")
            if _SECRET_PATTERN.search(value):
                raise HTTPException(
                    status_code=422,
                    detail="Skill payload contains a credential-like value",
                )
        elif value is not None and not isinstance(value, (bool, int, float)):
            raise HTTPException(status_code=422, detail="Skill payload contains unsupported data")

    walk(payload, 0)


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
