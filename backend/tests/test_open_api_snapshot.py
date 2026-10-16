"""Keep the checked-in Open API V1 snapshot aligned with the implementation."""

import json
from pathlib import Path

from app.main import app


def test_open_api_snapshot_covers_implementation_contract():
    snapshot_path = Path(__file__).parents[2] / "docs" / "open-api-v1.snapshot.json"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    implementation = app.openapi()

    assert snapshot["openapi"] == implementation["openapi"]
    for path in snapshot["paths"]:
        assert path in implementation["paths"]
    for schema in (
        "OpenAPIMessage",
        "OpenAPIChatRequest",
        "OpenAPIUsage",
        "OpenAPIChatResponse",
    ):
        assert schema in implementation["components"]["schemas"]
        assert snapshot["components"]["schemas"][schema]["properties"].keys() <= implementation[
            "components"
        ]["schemas"][schema]["properties"].keys()

    request_properties = snapshot["components"]["schemas"]["OpenAPIChatRequest"]["properties"]
    assert "api_key" not in request_properties
    assert "base_url" not in request_properties
