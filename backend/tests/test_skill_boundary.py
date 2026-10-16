"""A5: community skills are declarative prompt data, never executable plugins."""

import pytest
from fastapi import HTTPException

from app.services.skill_safety import (
    render_skill_prompt,
    validate_public_skill_text,
    validate_skill_payload,
)


def test_skill_rendering_uses_literal_placeholders_only():
    assert render_skill_prompt("Ask {topic} in {language}", {"topic": "社区参与", "language": "中文"}) == "Ask 社区参与 in 中文"


@pytest.mark.parametrize("value", ["api_key=secret-value", "__import__('os')", "<script>alert(1)</script>"])
def test_public_skill_data_rejects_secrets_and_executable_markers(value):
    with pytest.raises(HTTPException):
        validate_public_skill_text(value, field="prompt_template", max_chars=20_000)


def test_skill_rendering_rejects_nested_context_instead_of_evaluating_it():
    with pytest.raises(HTTPException):
        render_skill_prompt("{payload}", {"payload": {"command": "run"}})


@pytest.mark.parametrize(
    "payload",
    [
        {"api_key": "sk-test"},
        {"tool_calls": []},
        {"nested": {"command": "run"}},
        {"text": "api_key=sk-test"},
    ],
)
def test_skill_execution_payload_rejects_credentials_and_control_fields(payload):
    with pytest.raises(HTTPException):
        validate_skill_payload(payload)


def test_skill_execution_payload_rejects_deep_or_oversized_shapes():
    deep = value = {}
    for _ in range(9):
        value["nested"] = {}
        value = value["nested"]
    with pytest.raises(HTTPException):
        validate_skill_payload(deep)

    with pytest.raises(HTTPException):
        validate_skill_payload({"text": "x" * 100_001})
