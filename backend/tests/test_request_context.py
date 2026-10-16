"""Request correlation tests for the public HTTP boundary."""

import re

import pytest

from app.middleware.request_context import normalize_request_id


class TestRequestContext:
    def test_preserves_safe_client_request_id(self):
        assert normalize_request_id("research-run-123") == "research-run-123"

    @pytest.mark.parametrize("value", ["", "bad id", "bad\r\nheader", "x" * 129])
    def test_replaces_unsafe_client_request_id(self, value):
        request_id = normalize_request_id(value)

        assert request_id != value
        assert re.fullmatch(r"[0-9a-f]{32}", request_id)

    @pytest.mark.asyncio
    async def test_response_echoes_safe_request_id(self, client):
        response = await client.get(
            "/health",
            headers={"X-Request-ID": "research-run-123"},
        )

        assert response.status_code == 200
        assert response.headers["X-Request-ID"] == "research-run-123"

    @pytest.mark.asyncio
    async def test_response_generates_request_id_when_missing(self, client):
        response = await client.get("/health")

        assert response.status_code == 200
        assert re.fullmatch(r"[0-9a-f]{32}", response.headers["X-Request-ID"])
