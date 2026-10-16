"""Contract tests for provider discovery and the authenticated Open API."""

import pytest
import httpx

from app.api.deps import get_provider_registry
from app.main import app
from app.providers import FakeProvider, OpenAICompatibleProvider, ProviderRegistry
from app.providers.contracts import ProviderError


@pytest.fixture
def fake_registry():
    registry = ProviderRegistry([FakeProvider(response="deterministic answer", chunks=("det", "erministic"))])
    app.dependency_overrides[get_provider_registry] = lambda: registry
    yield registry
    app.dependency_overrides.pop(get_provider_registry, None)


class TestProviderContract:
    @pytest.mark.asyncio
    async def test_fake_provider_is_deterministic_and_streams(self, fake_registry):
        provider = fake_registry.get("fake")
        response = await provider.chat([{"role": "user", "content": "hello"}])
        chunks = [chunk async for chunk in provider.chat_stream([])]

        assert response.content == "deterministic answer"
        assert chunks == ["det", "erministic"]
        assert response.usage.total_tokens == 1

    @pytest.mark.asyncio
    async def test_capability_manifest_does_not_expose_provider_configuration(self, fake_registry):
        manifest = fake_registry.manifests()[0]

        assert manifest == {
            "id": "fake",
            "label": "Local fake provider",
            "configured": True,
            "capabilities": ["chat", "stream", "health"],
            "default_model": "wenjin-fake-1",
        }
        assert "api_key" not in str(manifest)
        assert "base_url" not in str(manifest)

    @pytest.mark.asyncio
    async def test_open_api_uses_fake_provider_without_accepting_key(self, client, fake_registry):
        response = await client.post(
            "/api/v1/open-api/chat/completions",
            json={
                "provider": "fake",
                "messages": [{"role": "user", "content": "hello"}],
                "api_key": "should-be-rejected",
            },
        )

        assert response.status_code == 422

        response = await client.post(
            "/api/v1/open-api/chat/completions",
            json={
                "provider": "fake",
                "messages": [{"role": "user", "content": "hello"}],
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["content"] == "deterministic answer"
        assert body["provider"] == "fake"
        assert "api_key" not in response.text

    @pytest.mark.asyncio
    async def test_open_api_project_context_is_owner_scoped(self, client, db_session, fake_registry):
        from app.models.survey import SurveyProject, UserProfile

        foreign_profile = UserProfile(user_id=None, role="researcher")
        db_session.add(foreign_profile)
        await db_session.flush()
        foreign_project = SurveyProject(profile_id=foreign_profile.id, title="foreign")
        db_session.add(foreign_project)
        await db_session.commit()
        await db_session.refresh(foreign_project)

        response = await client.post(
            "/api/v1/open-api/chat/completions",
            json={
                "provider": "fake",
                "project_id": foreign_project.id,
                "messages": [{"role": "user", "content": "hello"}],
            },
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_openai_compatible_adapter_normalizes_chat_and_stream(self):
        seen: list[dict] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            seen.append({"url": str(request.url), "authorization": request.headers.get("authorization")})
            if request.url.path.endswith("/models"):
                return httpx.Response(200, json={"data": []})
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "normalized"}}],
                    "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
                },
            )

        transport = httpx.MockTransport(handler)

        def client_factory(**kwargs):
            return httpx.AsyncClient(transport=transport, **kwargs)

        provider = OpenAICompatibleProvider(
            api_key="server-only-secret",
            base_url="https://provider.example.invalid/v1",
            model="test-model",
            client_factory=client_factory,
        )
        response = await provider.chat([{"role": "user", "content": "hello"}])

        assert response.content == "normalized"
        assert response.usage.total_tokens == 5
        assert provider.manifest.public_dict()["configured"] is True
        assert "server-only-secret" not in str(provider.manifest.public_dict())
        assert seen[0]["authorization"] == "Bearer server-only-secret"

        assert await provider.health() is True

    @pytest.mark.asyncio
    async def test_openai_compatible_adapter_maps_upstream_errors_without_leaking_key(self):
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": {"message": "secret should not escape"}})

        transport = httpx.MockTransport(handler)
        provider = OpenAICompatibleProvider(
            api_key="server-only-secret",
            base_url="https://provider.example.invalid/v1",
            model="test-model",
            client_factory=lambda **kwargs: httpx.AsyncClient(transport=transport, **kwargs),
        )

        with pytest.raises(ProviderError) as error:
            await provider.chat([{"role": "user", "content": "hello"}])

        assert error.value.category == "upstream_rejected"
        assert "server-only-secret" not in str(error.value)
        assert "secret should not escape" not in str(error.value)
