"""Minimal standard-library client for Wenjin Open API V1.

This example sends only the Wenjin access token. Provider keys and upstream
URLs remain server-side deployment configuration.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class WenjinOpenAPIError(RuntimeError):
    """A safe client-side representation of an HTTP API failure."""

    def __init__(self, status_code: int, message: str, request_id: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.request_id = request_id


@dataclass
class WenjinClient:
    base_url: str
    access_token: str
    timeout: float = 30.0

    def __post_init__(self) -> None:
        self.base_url = self.base_url.rstrip("/")
        if not self.base_url or not self.access_token:
            raise ValueError("base_url and access_token are required")

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = Request(
            f"{self.base_url}{path}",
            data=body,
            method=method,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
                **({"Content-Type": "application/json"} if body is not None else {}),
            },
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            request_id = exc.headers.get("X-Request-ID")
            try:
                error_body = json.loads(exc.read().decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                error_body = {}
            message = str(error_body.get("detail") or error_body.get("error") or "Wenjin API request failed")
            raise WenjinOpenAPIError(exc.code, message, request_id) from None
        except (URLError, TimeoutError) as exc:
            raise WenjinOpenAPIError(0, "Wenjin API is unreachable") from exc

    def providers(self) -> dict:
        return self._request("GET", "/api/v1/open-api/providers")

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        provider: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        project_id: int | None = None,
    ) -> dict:
        payload = {
            "messages": messages,
            "provider": provider,
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "project_id": project_id,
        }
        return self._request("POST", "/api/v1/open-api/chat/completions", payload)


if __name__ == "__main__":
    # Supply these values from a local secret store or shell; do not commit them.
    import os

    client = WenjinClient(
        os.environ["WENJIN_BASE_URL"],
        os.environ["WENJIN_ACCESS_TOKEN"],
    )
    print(client.chat([{"role": "user", "content": "请用一句话说明研究问题需要先界定的范围。"}]))
