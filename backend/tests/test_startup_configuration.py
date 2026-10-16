"""Regression tests for settings required by the real application startup path."""

from app.config import Settings


def test_auto_create_schema_has_safe_default() -> None:
    settings = Settings(_env_file=None, jwt_secret="t" * 32)

    assert settings.auto_create_schema is False
