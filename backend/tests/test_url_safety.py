"""URL boundary tests for provider-facing upload URLs."""

import pytest

from app.services.url_safety import (
    build_public_upload_url,
    validate_public_base_url,
)


class TestPublicURLSafety:
    def test_accepts_https_public_hostname(self):
        assert validate_public_base_url("https://research.example.org/") == (
            "https://research.example.org"
        )

    @pytest.mark.parametrize(
        "value",
        [
            "",
            "http://research.example.org",
            "https://localhost",
            "https://127.0.0.1",
            "https://10.0.0.5",
            "https://[::1]",
            "https://user:password@research.example.org",
            "https://research.example.org/path?secret=value",
        ],
    )
    def test_rejects_unsafe_public_base_url(self, value):
        with pytest.raises(ValueError):
            validate_public_base_url(value)

    def test_builds_url_from_server_filename_only(self):
        assert build_public_upload_url(
            "https://research.example.org",
            "abc123.wav",
        ) == "https://research.example.org/uploads/abc123.wav"

    def test_encodes_path_separators_and_untrusted_filename(self):
        assert build_public_upload_url(
            "https://research.example.org",
            "../private.txt",
        ) == "https://research.example.org/uploads/..%2Fprivate.txt"
