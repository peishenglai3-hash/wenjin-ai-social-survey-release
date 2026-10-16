"""Refresh-token hashing and HttpOnly cookie regression tests."""

import pytest
from fastapi import Response
from sqlalchemy import select
from starlette.requests import Request

from app.api.v1.router_auth import refresh
from app.config import settings
from app.core.refresh_tokens import hash_refresh_token
from app.core.security import create_refresh_token, hash_password
from app.models.user import UserAccount


def _request_with_cookie(token: str) -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/auth/refresh",
        "raw_path": b"/api/v1/auth/refresh",
        "query_string": b"",
        "headers": [
            (
                b"cookie",
                f"{settings.refresh_cookie_name}={token}".encode("ascii"),
            )
        ],
        "scheme": "http",
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 50000),
    }
    return Request(scope)


@pytest.mark.asyncio
async def test_refresh_cookie_rotates_and_stores_only_digest(db_session):
    user = UserAccount(
        email="refresh-cookie@example.invalid",
        hashed_password=hash_password("test-password"),
        display_name="Refresh Cookie",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    presented = create_refresh_token(user.id, user.email)
    user.refresh_token = hash_refresh_token(presented)
    await db_session.commit()

    response = Response()
    result = await refresh(
        request=_request_with_cookie(presented),
        response=response,
        body=None,
        db=db_session,
    )

    assert result.access_token
    assert not hasattr(result, "refresh_token")
    set_cookie = response.headers["set-cookie"]
    rotated = set_cookie.split(f"{settings.refresh_cookie_name}=", 1)[1].split(";", 1)[0]
    assert rotated != presented
    assert user.refresh_token == hash_refresh_token(rotated)
    assert presented not in user.refresh_token
    assert f"{settings.refresh_cookie_name}=" in set_cookie
    assert "HttpOnly" in set_cookie


@pytest.mark.asyncio
async def test_legacy_plaintext_refresh_token_is_upgraded(db_session):
    user = UserAccount(
        email="refresh-legacy@example.invalid",
        hashed_password=hash_password("test-password"),
        display_name="Legacy Refresh",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    presented = create_refresh_token(user.id, user.email)
    user.refresh_token = presented
    await db_session.commit()

    response = Response()
    result = await refresh(
        request=_request_with_cookie(presented),
        response=response,
        body=None,
        db=db_session,
    )

    assert result.access_token
    assert not hasattr(result, "refresh_token")
    set_cookie = response.headers["set-cookie"]
    rotated = set_cookie.split(f"{settings.refresh_cookie_name}=", 1)[1].split(";", 1)[0]
    assert rotated != presented
    assert user.refresh_token == hash_refresh_token(rotated)
    assert await db_session.scalar(
        select(UserAccount.refresh_token).where(UserAccount.id == user.id)
    ) != presented
