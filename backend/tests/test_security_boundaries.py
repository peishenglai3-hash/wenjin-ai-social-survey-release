"""Regression tests for request-size and proxy-aware rate-limit boundaries."""

from starlette.requests import Request
from starlette.responses import PlainTextResponse

from app.main import request_size_middleware
from app.middleware.rate_limit import RateLimitMiddleware


def _request(
    *,
    client_host: str = "10.0.0.8",
    headers: dict[str, str] | None = None,
) -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/test",
        "headers": [(key.lower().encode(), value.encode()) for key, value in (headers or {}).items()],
        "client": (client_host, 12345),
        "server": ("test", 80),
        "scheme": "http",
    }
    return Request(scope)


async def _next(request):
    return PlainTextResponse("ok")


async def test_invalid_content_length_is_a_client_error():
    response = await request_size_middleware(
        _request(headers={"content-length": "not-a-number"}),
        _next,
    )

    assert response.status_code == 400


async def test_negative_content_length_is_a_client_error():
    response = await request_size_middleware(
        _request(headers={"content-length": "-1"}),
        _next,
    )

    assert response.status_code == 400


def test_untrusted_peer_cannot_spoof_forwarded_ip():
    limiter = RateLimitMiddleware(lambda scope, receive, send: None)
    request = _request(
        client_host="10.0.0.8",
        headers={"X-Forwarded-For": "203.0.113.9", "X-Real-IP": "203.0.113.10"},
    )

    assert limiter._get_client_ip(request) == "10.0.0.8"


def test_trusted_proxy_can_supply_a_valid_forwarded_ip():
    limiter = RateLimitMiddleware(
        lambda scope, receive, send: None,
        trusted_proxy_ips=["10.0.0.0/24"],
    )
    request = _request(
        client_host="10.0.0.8",
        headers={"X-Forwarded-For": "203.0.113.9, 10.0.0.1"},
    )

    assert limiter._get_client_ip(request) == "203.0.113.9"


def test_trusted_proxy_ignores_invalid_forwarded_ip():
    limiter = RateLimitMiddleware(
        lambda scope, receive, send: None,
        trusted_proxy_ips=["10.0.0.8"],
    )
    request = _request(
        client_host="10.0.0.8",
        headers={"X-Forwarded-For": "not-an-ip"},
    )

    assert limiter._get_client_ip(request) == "10.0.0.8"
