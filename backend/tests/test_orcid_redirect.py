"""OAuth redirect validation tests."""

import pytest

from app.services.orcid_service import normalize_redirect_path


def test_orcid_redirect_accepts_same_origin_path_and_query() -> None:
    assert normalize_redirect_path("/orcid-callback?next=fieldwork") == (
        "/orcid-callback?next=fieldwork"
    )


@pytest.mark.parametrize(
    "value",
    [
        "https://evil.example/steal",
        "//evil.example/steal",
        "javascript:alert(1)",
        "fieldwork",
        r"/\\evil.example",
    ],
)
def test_orcid_redirect_rejects_cross_origin_or_ambiguous_values(value: str) -> None:
    with pytest.raises(ValueError):
        normalize_redirect_path(value)
