"""Regression tests for public request and telemetry privacy bounds."""

import pytest
from pydantic import ValidationError

from app.schemas.open_api import OpenAPIChatRequest
from app.services.analytics_service import _sanitize_properties


def test_open_api_rejects_oversized_combined_prompt() -> None:
    with pytest.raises(ValidationError, match="combined message content"):
        OpenAPIChatRequest(
            messages=[
                {"role": "system", "content": "x" * 100_000},
                {"role": "user", "content": "y" * 100_000},
                {"role": "assistant", "content": "z"},
            ]
        )


def test_public_analytics_keeps_allowlisted_bounded_metadata_only() -> None:
    safe = _sanitize_properties({
        "query": "private transcript",
        "query_length": 12,
        "filter_keys": ["method", "private_filter"],
        "page": "literature",
        "nested": {"private": "data"},
    })

    assert safe == {
        "query_length": 12,
        "filter_keys": ["method"],
        "page": "literature",
    }
