from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

# ── Structured logging to console + file ──────────────────────────
import logging
import sys


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stderr),
    ],
)
# Silence noisy third-party loggers
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

from app.config import settings
from app.core.events import lifespan
from app.api.v1.router import api_router, protected_api_router
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.request_context import RequestContextMiddleware

app = FastAPI(
    title="AI Social Survey API",
    version="0.5.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Accept", "Authorization", "Content-Type"],
)

# Security headers (OWASP recommended)
app.add_middleware(SecurityHeadersMiddleware)

# Rate limiting (per-IP sliding window)
app.add_middleware(
    RateLimitMiddleware,
    enabled=settings.rate_limit_enabled,
    default_rpm=settings.rate_limit_api_per_minute,
    ai_rpm=settings.rate_limit_ai_per_minute,
    auth_rpm=settings.rate_limit_auth_per_minute,
    trusted_proxy_ips=settings.trusted_proxy_ips,
)

# Correlate requests without trusting arbitrary client header values.
app.add_middleware(RequestContextMiddleware)


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Return a small compatible error envelope without echoing arbitrary input."""
    message = exc.detail if isinstance(exc.detail, str) else "Request failed"
    return JSONResponse(
        status_code=exc.status_code,
        headers=exc.headers,
        content={
            "error": message,
            "detail": message,
            "request_id": _request_id(request),
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Avoid FastAPI's default body echo, which may repeat a supplied secret."""
    issues = [
        {
            "loc": list(error.get("loc", ())),
            "msg": error.get("msg", "Invalid value"),
            "type": error.get("type", "value_error"),
        }
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={
            "error": "Request validation failed",
            "detail": issues,
            "request_id": _request_id(request),
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Keep stack traces in server logs, never in public responses."""
    del exc
    logging.getLogger(__name__).exception(
        "unhandled_request_exception request_id=%s", _request_id(request), exc_info=True
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "request_id": _request_id(request),
        },
    )


# ── Request size guard ──────────────────────────────────────────────
SIZE_LIMITS: dict[str, int] = {
    "transcribe-file": 510 * 1024 * 1024,  # 500MB + margin
    "upload-reference": 11 * 1024 * 1024,  # 10MB + margin
    "analyze": 11 * 1024 * 1024,           # image analyze
}


@app.middleware("http")
async def request_size_middleware(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            size = int(content_length)
        except (TypeError, ValueError):
            return JSONResponse(
                status_code=400,
                content={"error": "无效的 Content-Length"},
            )
        if size < 0:
            return JSONResponse(
                status_code=400,
                content={"error": "无效的 Content-Length"},
            )
        path = request.url.path
        limit = 0
        for key, lim in SIZE_LIMITS.items():
            if key in path:
                limit = lim
                break
        if limit == 0:
            limit = 50 * 1024 * 1024
        if size > limit:
            limit_mb = limit / (1024 * 1024)
            return JSONResponse(
                status_code=413,
                content={
                    "error": f"请求体过大（{size / (1024 * 1024):.1f}MB），"
                             f"该端点最大允许 {limit_mb:.0f}MB"
                },
            )
    return await call_next(request)

app.include_router(api_router, prefix="/api/v1")
app.include_router(protected_api_router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.5.0"}
