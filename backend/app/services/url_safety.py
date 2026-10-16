"""Safety checks for URLs sent to external providers."""

from ipaddress import ip_address
from urllib.parse import quote, urlsplit


def validate_public_base_url(value: str) -> str:
    """Validate a deployment-owned HTTPS base URL for provider callbacks.

    This function intentionally accepts only deployment configuration, never a
    user-supplied URL. Literal loopback, private, link-local and other special
    IP ranges are rejected so a misconfigured callback cannot become an SSRF
    primitive for a provider.
    """

    raw = (value or "").strip().rstrip("/")
    if not raw:
        raise ValueError("PUBLIC_BASE_URL is required")

    try:
        parsed = urlsplit(raw)
        hostname = parsed.hostname
    except ValueError as exc:
        raise ValueError("PUBLIC_BASE_URL is invalid") from exc

    if parsed.scheme != "https" or not hostname:
        raise ValueError("PUBLIC_BASE_URL must be an HTTPS URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("PUBLIC_BASE_URL must not contain credentials, query, or fragment")
    if hostname.lower() in {"localhost", "localhost.localdomain"} or hostname.lower().endswith(".local"):
        raise ValueError("PUBLIC_BASE_URL must not target a local hostname")

    try:
        address = ip_address(hostname)
    except ValueError:
        address = None

    if address and (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    ):
        raise ValueError("PUBLIC_BASE_URL must not target a special-use IP address")

    return raw


def build_public_upload_url(base_url: str, filename: str) -> str:
    """Build a provider URL from a validated base and a server filename."""

    base = validate_public_base_url(base_url)
    if not filename or filename in {".", ".."}:
        raise ValueError("uploaded filename is required")
    return f"{base}/uploads/{quote(filename, safe='')}"
