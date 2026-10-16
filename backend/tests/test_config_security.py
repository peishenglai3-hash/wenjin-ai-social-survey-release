import pytest

from app.config import Settings


def _secret():
    return "test-only-jwt-secret-012345678901234567890123"


def test_cors_origins_require_explicit_http_origins():
    settings = Settings(jwt_secret=_secret(), cors_origins=["https://research.example.org/"])
    assert settings.cors_origins == ["https://research.example.org"]


@pytest.mark.parametrize(
    "origins",
    [["*"], ["https://example.org/path"], ["ftp://example.org"], ["https://user:pass@example.org"]],
)
def test_cors_origins_reject_wildcard_or_malformed_values(origins):
    with pytest.raises(ValueError):
        Settings(jwt_secret=_secret(), cors_origins=origins)
