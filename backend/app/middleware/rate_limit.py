"""Rate limiter middleware — sliding window per IP + endpoint category.

Uses Redis sorted-set sliding window in production with seamless
in-memory fallback when Redis is unavailable.
"""

import ipaddress

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.services.rate_limit_store import get_rate_limit_store


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limit requests per real-IP (respects X-Forwarded-For from nginx)
    with per-endpoint category limits.

    Architecture:
    - check_and_increment() hits Redis sorted sets in production
    - Falls back to in-memory dict if Redis is unreachable
    - No configuration change needed — transparent to the rest of the stack
    """

    def __init__(
        self,
        app,
        default_rpm: int = 60,
        ai_rpm: int = 10,
        auth_rpm: int = 20,
        enabled: bool = True,
        trusted_proxy_ips: list[str] | None = None,
    ):
        super().__init__(app)
        self.default_rpm = default_rpm
        self.ai_rpm = ai_rpm
        self.auth_rpm = auth_rpm
        self.enabled = enabled
        self.trusted_proxy_networks = self._parse_trusted_proxies(trusted_proxy_ips or [])

    @staticmethod
    def _parse_trusted_proxies(values: list[str]) -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
        networks = []
        for value in values:
            try:
                networks.append(ipaddress.ip_network(value, strict=False))
            except ValueError:
                continue
        return tuple(networks)

    def _peer_is_trusted(self, request: Request) -> bool:
        peer = request.client.host if request.client else ""
        try:
            peer_ip = ipaddress.ip_address(peer)
        except ValueError:
            return False
        return any(peer_ip in network for network in self.trusted_proxy_networks)

    @staticmethod
    def _valid_ip(value: str) -> str | None:
        try:
            return str(ipaddress.ip_address(value.strip()))
        except ValueError:
            return None

    def _get_client_ip(self, request: Request) -> str:
        """Get real client IP, respecting reverse proxy headers."""
        peer = request.client.host if request.client else "unknown"
        if not self._peer_is_trusted(request):
            return peer
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            client_ip = self._valid_ip(forwarded.split(",")[0])
            if client_ip:
                return client_ip
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            client_ip = self._valid_ip(real_ip)
            if client_ip:
                return client_ip
        return peer

    def _category(self, path: str) -> tuple[int, str]:
        """Classify the request path into a rate-limit category.

        Returns (limit_rpm, category_label).
        """
        # Health check is always free
        if path == "/health":
            return 999999, "health"

        # CAPTCHA and /me are read-only, exempt from auth limits
        if "/auth/captcha" in path or path.endswith("/auth/me"):
            return self.default_rpm, "api"

        # Auth endpoints (login, register, refresh, etc.) — stricter limit
        if "/auth/" in path:
            return self.auth_rpm, "auth"

        # AI-heavy endpoints — most restrictive limit
        if any(p in path for p in [
            "/copilot/", "/topic/", "/analysis/", "/export/",
            "/skills/", "/fieldwork/hints", "/fieldwork/summarize",
        ]):
            return self.ai_rpm, "ai"

        return self.default_rpm, "api"

    async def dispatch(self, request: Request, call_next):
        if not self.enabled:
            return await call_next(request)
        client_ip = self._get_client_ip(request)
        limit, category = self._category(request.url.path)
        key = f"{client_ip}:{category}"

        store = get_rate_limit_store()
        allowed, count, retry_or_remaining = await store.check_and_increment(
            key, window_s=60, limit=limit
        )

        if not allowed:
            retry_after = retry_or_remaining
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Too many requests",
                    "retry_after_seconds": retry_after,
                    "limit": f"{limit}/minute",
                    "category": category,
                },
                headers={"Retry-After": str(retry_after)},
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(retry_or_remaining)
        return response
