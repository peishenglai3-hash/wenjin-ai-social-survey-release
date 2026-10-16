"""Provider configuration boundary tests."""

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.services.ai import AIService


class TestProviderBoundary:
    @pytest.fixture
    def unconfigured_service(self):
        return AIService(api_key="", base_url="https://api.example.invalid/v1")

    @pytest.mark.asyncio
    async def test_chat_fails_closed_without_provider(self, unconfigured_service):
        with patch("app.services.ai.AsyncClient") as async_client:
            with pytest.raises(HTTPException) as error:
                await unconfigured_service.chat([
                    {"role": "user", "content": "hello"},
                ])

        assert error.value.status_code == 503
        assert "provider" in str(error.value.detail).lower()
        async_client.assert_not_called()

    @pytest.mark.asyncio
    async def test_stream_fails_closed_without_provider(self, unconfigured_service):
        with patch("app.services.ai.AsyncClient") as async_client:
            with pytest.raises(HTTPException) as error:
                async for _ in unconfigured_service.chat_stream([
                    {"role": "user", "content": "hello"},
                ]):
                    pass

        assert error.value.status_code == 503
        async_client.assert_not_called()

    @pytest.mark.asyncio
    async def test_health_does_not_call_external_host_without_provider(
        self,
        unconfigured_service,
    ):
        with patch("app.services.ai.AsyncClient") as async_client:
            assert await unconfigured_service.health() is False

        async_client.assert_not_called()
