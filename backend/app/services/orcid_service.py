"""ORCID OAuth 2.0 / OpenID Connect service.

Flow:
  1. GET /auth/orcid          → redirect to ORCID authorize page
  2. User authorizes          → ORCID redirects to our callback
  3. GET /auth/orcid/callback → exchange code → get ORCID iD → login/bind/create

State parameter carries a signed JWT to avoid server-side state storage.
"""

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlencode, urlsplit

import httpx
from jose import JWTError, jwt

from app.config import settings

logger = logging.getLogger(__name__)

# State token config
_STATE_SECRET = settings.jwt_secret  # reuse app JWT secret for state signing
_STATE_EXPIRE_MINUTES = 10


def normalize_redirect_path(value: str | None) -> str:
    """Allow only a same-origin frontend path in the signed OAuth state.

    OAuth callbacks must never redirect to a client-controlled absolute URL.
    Query parameters are allowed because the value is encoded as data in the
    final callback URL, but schemes, hosts, network-path references and
    backslashes are rejected.
    """
    raw = (value or "/").strip()
    if len(raw) > 512 or "\\" in raw:
        raise ValueError("redirect path is invalid")
    parsed = urlsplit(raw)
    if parsed.scheme or parsed.netloc or not parsed.path.startswith("/"):
        raise ValueError("redirect path must be same-origin")
    if raw.startswith("//"):
        raise ValueError("redirect path must be same-origin")
    return raw


def _build_state_token(redirect_to: str = "/") -> str:
    """Build a signed state token carrying redirect destination + nonce."""
    redirect_to = normalize_redirect_path(redirect_to)
    payload = {
        "nonce": secrets.token_hex(16),
        "redirect_to": redirect_to,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=_STATE_EXPIRE_MINUTES),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, _STATE_SECRET, algorithm="HS256")


def decode_state_token(state: str) -> Optional[dict]:
    """Decode and validate a state token. Returns None if invalid/expired."""
    try:
        return jwt.decode(state, _STATE_SECRET, algorithms=["HS256"])
    except JWTError:
        return None


def get_authorize_url(redirect_to: str = "/") -> tuple[str, str]:
    """Generate the ORCID OAuth authorize URL and state token.

    Returns (authorize_url, state_token).
    The frontend should store the state_token and pass it to the callback.
    """
    redirect_to = normalize_redirect_path(redirect_to)
    state = _build_state_token(redirect_to)
    sandbox = settings.orcid_sandbox
    base_url = "https://sandbox.orcid.org" if sandbox else "https://orcid.org"

    params = {
        "client_id": settings.orcid_client_id,
        "response_type": "code",
        "scope": "openid",
        "redirect_uri": settings.orcid_redirect_uri,
        "state": state,
    }
    query = urlencode(params)
    url = f"{base_url}/oauth/authorize?{query}"
    return url, state


async def exchange_code(code: str) -> dict:
    """Exchange authorization code for tokens + ORCID iD.

    Returns dict with keys: orcid, access_token, id_token, name (if available).

    Raises ValueError on failure.
    """
    sandbox = settings.orcid_sandbox
    token_url = "https://sandbox.orcid.org/oauth/token" if sandbox else "https://orcid.org/oauth/token"

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            token_url,
            data={
                "client_id": settings.orcid_client_id,
                "client_secret": settings.orcid_client_secret,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.orcid_redirect_uri,
            },
            headers={"Accept": "application/json"},
        )
        if resp.status_code != 200:
            # The response may contain provider diagnostics or reflected
            # credentials. Keep it out of logs and the public exception.
            logger.error("ORCID token exchange failed: status=%s", resp.status_code)
            raise ValueError(f"ORCID token exchange failed: {resp.status_code}")

        token_data = resp.json()
        orcid_id = token_data.get("orcid")
        access_token = token_data.get("access_token")
        id_token_raw = token_data.get("id_token")

        if not orcid_id:
            raise ValueError("ORCID iD not found in token response")

        # Try to get display name from userinfo endpoint
        name = None
        if access_token:
            try:
                userinfo_url = "https://orcid.org/oauth/userinfo"
                ui_resp = await client.get(
                    userinfo_url,
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                if ui_resp.status_code == 200:
                    ui = ui_resp.json()
                    name = ui.get("name") or ui.get("given_name")
                    if name and ui.get("family_name"):
                        name = f"{ui.get('given_name', '')} {ui.get('family_name', '')}".strip()
            except Exception:
                logger.warning("ORCID userinfo fetch failed, using iD as name", exc_info=True)

        return {
            "orcid": orcid_id,
            "access_token": access_token,
            "id_token": id_token_raw,
            "name": name or f"ORCID:{orcid_id[-8:]}",
        }
