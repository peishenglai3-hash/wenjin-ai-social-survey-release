"""Hash and compare refresh tokens before they reach persistent storage."""

import hashlib
import hmac

from app.config import settings


def hash_refresh_token(token: str) -> str:
    """Create a keyed digest suitable for storage instead of the raw JWT."""

    return hmac.new(
        settings.jwt_secret.encode("utf-8"),
        token.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def matches_refresh_token(stored: str | None, presented: str) -> bool:
    """Match new digests and one-time legacy plaintext values during migration."""

    if not stored or not presented:
        return False
    candidate = hash_refresh_token(presented)
    if hmac.compare_digest(stored, candidate):
        return True
    # Legacy rows are accepted once so a successful rotation upgrades storage.
    return hmac.compare_digest(stored, presented)
