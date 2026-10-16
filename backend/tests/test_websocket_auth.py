from types import SimpleNamespace

from app.api.deps_auth import extract_websocket_bearer


def test_websocket_bearer_is_read_from_subprotocol_not_url():
    websocket = SimpleNamespace(headers={"sec-websocket-protocol": "bearer, eyJ.test.token"})
    assert extract_websocket_bearer(websocket) == "eyJ.test.token"


def test_websocket_bearer_rejects_missing_or_ambiguous_protocols():
    for header in ("", "bearer", "bearer, one, two", "token, eyJ.test.token"):
        websocket = SimpleNamespace(headers={"sec-websocket-protocol": header})
        assert extract_websocket_bearer(websocket) is None
