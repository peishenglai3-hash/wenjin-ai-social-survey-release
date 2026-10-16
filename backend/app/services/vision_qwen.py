"""Qwen Vision service — uses DashScope native multimodal API for image analysis.

DashScope compatible-mode/v1 endpoint is text-only; this module uses
DashScope's native multimodal-generation API for qwen-vl-max and similar models.
"""

import logging
from typing import AsyncGenerator

from httpx import AsyncClient

from app.config import settings

logger = logging.getLogger(__name__)

# DashScope native multimodal API endpoint
DASHSCOPE_MM_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"


class QwenVisionService:
    """Dedicated service for Qwen vision-language models via DashScope native API.

    Uses DashScope multimodal-generation API which properly supports
    image inputs (unlike the compatible-mode endpoint which is text-only).
    """

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or settings.qwen_api_key
        self.model = model or settings.qwen_vision_model

    @property
    def is_available(self) -> bool:
        return bool(self.api_key)

    async def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        task: str = "",
    ) -> str:
        """Fallback text-only chat via DashScope compatible-mode endpoint.

        Called by skills when vision analysis fails and text-only fallback is needed.
        Uses the DashScope text API (not multimodal) which supports qwen text models.
        """
        model = model or "qwen-max"
        async with AsyncClient(timeout=120) as client:
            resp = await client.post(
                "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
            )
            if resp.status_code != 200:
                raise RuntimeError(f"Qwen text chat failed ({resp.status_code}): {resp.text[:500]}")
            return resp.json()["choices"][0]["message"]["content"]

    async def analyze_image(
        self,
        prompt: str,
        image_base64: str,
        temperature: float = 0.6,
        max_tokens: int = 4096,
    ) -> str:
        """Analyze an image using Qwen-VL via DashScope multimodal API."""
        if not self.api_key:
            raise RuntimeError("Qwen API key not configured. Set QWEN_API_KEY in .env")

        image_data = f"data:image/jpeg;base64,{image_base64}"

        payload = {
            "model": self.model,
            "input": {
                "messages": [{
                    "role": "user",
                    "content": [
                        {"text": prompt},
                        {"image": image_data},
                    ],
                }]
            },
            "parameters": {
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        }

        async with AsyncClient(timeout=120) as client:
            resp = await client.post(
                DASHSCOPE_MM_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )

            if resp.status_code != 200:
                logger.error(
                    "Qwen Vision API error: status=%s model=%s image_len=%s",
                    resp.status_code,
                    self.model,
                    len(image_base64),
                )
                raise RuntimeError(f"Qwen Vision API returned {resp.status_code}")

            data = resp.json()
            try:
                output = data.get("output", {})
                choices = output.get("choices", [])
                if choices:
                    message = choices[0].get("message", {})
                    content = message.get("content", [])
                    if isinstance(content, list):
                        text_parts = []
                        for block in content:
                            if isinstance(block, dict) and "text" in block:
                                text_parts.append(block["text"])
                            elif isinstance(block, str):
                                text_parts.append(block)
                        return "".join(text_parts)
                    elif isinstance(content, str):
                        return content
                    return message.get("text", "") or str(content)
                text = output.get("text", "")
                if text:
                    return text
                logger.warning("Unexpected Qwen VL response structure")
                return ""
            except Exception as e:
                logger.exception("Failed to parse Qwen VL response structure")
                raise RuntimeError("Failed to parse Qwen VL response") from e

    async def analyze_image_stream(
        self,
        prompt: str,
        image_base64: str,
        temperature: float = 0.6,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        """Streaming version of analyze_image via DashScope SSE."""
        if not self.api_key:
            raise RuntimeError("Qwen API key not configured.")

        image_data = f"data:image/jpeg;base64,{image_base64}"

        payload = {
            "model": self.model,
            "input": {
                "messages": [{
                    "role": "user",
                    "content": [
                        {"text": prompt},
                        {"image": image_data},
                    ],
                }]
            },
            "parameters": {
                "temperature": temperature,
                "max_tokens": max_tokens,
                "incremental_output": True,
            },
        }

        async with AsyncClient(timeout=180) as client:
            async with client.stream(
                "POST",
                DASHSCOPE_MM_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            ) as resp:
                if resp.status_code != 200:
                    error_body = await resp.aread()
                    raise RuntimeError(f"Qwen Vision streaming error ({resp.status_code}): {error_body[:500]}")

                async for line in resp.aiter_lines():
                    if line.startswith("data:"):
                        data_str = line[5:].strip()
                        if not data_str or data_str == "[DONE]":
                            continue
                        try:
                            import json
                            chunk = json.loads(data_str)
                            output = chunk.get("output", {})
                            choices = output.get("choices", [])
                            if choices:
                                delta = choices[0].get("message", {}).get("content", [])
                                if isinstance(delta, list):
                                    for block in delta:
                                        if isinstance(block, dict) and "text" in block:
                                            yield block["text"]
                                        elif isinstance(block, str):
                                            yield block
                                elif isinstance(delta, str):
                                    yield delta
                            text = output.get("text", "")
                            if text:
                                yield text
                        except Exception:
                            logger.debug("Failed to parse Qwen VL streaming chunk", exc_info=True)
                            continue


# Singleton
qwen_vision = QwenVisionService()
