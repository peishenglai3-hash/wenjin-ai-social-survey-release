"""Request correlation context for safe diagnostics and client support."""

from contextvars import ContextVar
import logging
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


def get_request_id() -> str | None:
    """Return the current safe correlation id for logs and audit metadata."""
    return request_id_context.get()


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
            logging.getLogger(__name__).info(
                "request_completed request_id=%s method=%s path=%s status=%s",
                request_id,
                request.method,
                request.url.path,
                response.status_code,
            )
            return response
        except Exception:
            logging.getLogger(__name__).exception(
                "request_failed request_id=%s method=%s path=%s",
                request_id,
                request.method,
                request.url.path,
            )
            raise
        finally:
            request_id_context.reset(context_token)
