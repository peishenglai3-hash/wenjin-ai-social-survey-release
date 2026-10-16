"""Request correlation context for safe diagnostics and client support."""

from contextvars import ContextVar
import re
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


REQUEST_ID_HEADER = "X-Request-ID"
_REQUEST_ID_PATTERN = re.compile(r"[A-Za-z0-9._:-]{1,128}")
request_id_context: ContextVar[str | None] = ContextVar(
    "wenjin_request_id",
    default=None,
)


def normalize_request_id(value: str | None) -> str:
    """Return a bounded, header-safe request id or generate a new one.

    Client-provided IDs are useful for tracing, but must not be copied into a
    response or log unless they match a conservative allow-list. In particular,
    this rejects CR/LF and whitespace that could enable header/log injection.
    """

    candidate = (value or "").strip()
    if candidate and _REQUEST_ID_PATTERN.fullmatch(candidate):
        return candidate
    return uuid4().hex


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach a safe correlation ID to request state and the response header."""

    async def dispatch(self, request: Request, call_next):
        request_id = normalize_request_id(request.headers.get(REQUEST_ID_HEADER))
        request.state.request_id = request_id
        context_token = request_id_context.set(request_id)
        try:
            response = await call_next(request)
            response.headers[REQUEST_ID_HEADER] = request_id
            return response
        finally:
            request_id_context.reset(context_token)
