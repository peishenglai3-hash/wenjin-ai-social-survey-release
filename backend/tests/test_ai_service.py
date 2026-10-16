"""Unit tests for AIService — model routing, chat, streaming, error handling."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.ai import AIService, VisionNotSupportedError, TASK_MODELS, TASK_MAX_TOKENS


class TestModelRouting:
    """Verify task → model routing logic."""

    def test_known_task_gets_specific_model(self):
        svc = AIService(api_key="sk-test", base_url="https://api.test.com/v1")
        assert svc._model_for("topic") == "deepseek-v4-pro"
        assert svc._model_for("hints") == "deepseek-v4-flash"
        assert svc._model_for("questionnaire") == "deepseek-v4-pro"

    def test_unknown_task_gets_default_model(self):
        svc = AIService(api_key="sk-test", base_url="https://api.test.com/v1")
        assert svc._model_for("nonexistent_task") == "deepseek-v4-pro"

    def test_task_max_tokens_falls_back_to_default(self):
        svc = AIService(api_key="sk-test", base_url="https://api.test.com/v1")
        assert svc._max_tokens_for("topic") == 8192
        assert svc._max_tokens_for("hints") == 1024
        assert svc._max_tokens_for("unknown") == 4096


class TestAIServiceChat:
    """Test the chat() method with mocked HTTP responses."""

    @pytest.fixture
    def svc(self):
        return AIService(api_key="sk-test", base_url="https://api.test.com/v1")

    @pytest.mark.asyncio
    async def test_chat_returns_content_on_success(self, svc):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "Hello, world!"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }

        with patch("httpx.AsyncClient.post", return_value=mock_resp):
            with patch.object(svc, "_model_for", return_value="deepseek-v4-pro"):
                result = await svc.chat(
                    [{"role": "user", "content": "Hi"}],
                    max_tokens=512,
                )
        assert result == "Hello, world!"

    @pytest.mark.asyncio
    async def test_chat_passes_correct_model_in_request(self, svc):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "ok"}}],
            "usage": {},
        }

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = mock_resp
            await svc.chat([{"role": "user", "content": "Hi"}], model="test-model")
            call_args = mock_post.call_args
            sent_json = call_args[1]["json"]
            assert sent_json["model"] == "test-model"

    @pytest.mark.asyncio
    async def test_chat_raises_on_http_error(self, svc):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.raise_for_status.side_effect = Exception("Server Error")

        with patch("httpx.AsyncClient.post", return_value=mock_resp):
            with pytest.raises(Exception, match="Server Error"):
                await svc.chat([{"role": "user", "content": "Hi"}])

    @pytest.mark.asyncio
    async def test_task_token_ceiling_does_not_expand_small_request(self, svc):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "ok"}}],
            "usage": {},
        }

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = mock_resp
            await svc.chat(
                [{"role": "user", "content": "Hi"}],
                task="hints",
                max_tokens=8192,
            )
        assert mock_post.call_args.kwargs["json"]["max_tokens"] == 1024

    @pytest.mark.asyncio
    async def test_image_uses_routed_provider_credentials(self):
        svc = AIService(
            api_key="",
            base_url="https://primary.example/v1",
            fallback_qwen_key="qwen-test",
            fallback_qwen_base="https://qwen.example/v1",
        )
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "ok"}}],
        }

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = mock_resp
            result = await svc.chat_with_image("describe", "ZmFrZQ==")

        assert result == "ok"
        assert mock_post.call_args.args[0] == "https://qwen.example/v1/chat/completions"
        assert mock_post.call_args.kwargs["headers"] == {"Authorization": "Bearer qwen-test"}


class TestAIServiceStreaming:
    """Test the chat_stream() method."""

    @pytest.fixture
    def svc(self):
        return AIService(api_key="sk-test", base_url="https://api.test.com/v1")

    @pytest.mark.asyncio
    async def test_stream_yields_tokens(self, svc):
        class MockStreamResponse:
            def raise_for_status(self):
                pass  # no-op for test

            async def aiter_lines(self):
                for line in [
                    'data: {"choices":[{"delta":{"content":"Hello"}}]}',
                    'data: {"choices":[{"delta":{"content":" world"}}]}',
                    'data: [DONE]',
                ]:
                    yield line

        mock_resp = MockStreamResponse()

        with patch("httpx.AsyncClient.stream") as mock_stream:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__.return_value = mock_resp
            mock_stream.return_value = mock_ctx

            tokens = []
            async for token in svc.chat_stream(
                [{"role": "user", "content": "Hi"}],
                max_tokens=512,
            ):
                tokens.append(token)

        assert "".join(tokens) == "Hello world"


class TestHealthCheck:
    """Test the health() method."""

    @pytest.mark.asyncio
    async def test_health_returns_true_when_api_reachable(self):
        svc = AIService(api_key="sk-test", base_url="https://api.test.com/v1")
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch("httpx.AsyncClient.get", return_value=mock_resp):
            assert await svc.health() is True

    @pytest.mark.asyncio
    async def test_health_returns_false_on_error(self):
        svc = AIService(api_key="sk-test", base_url="https://api.test.com/v1")
        with patch("httpx.AsyncClient.get", side_effect=Exception("Connection refused")):
            assert await svc.health() is False
