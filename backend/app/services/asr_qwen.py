"""Qwen / DashScope speech recognition — real-time WebSocket + file transcription.

File transcription uses the DashScope Python SDK's Recognition class
(paraformer-realtime-v2 via WebSocket, PCM streaming — no HTTPS URL needed).
"""

import asyncio
import json
import logging
import os
import time
from typing import AsyncGenerator

import websockets
from httpx import AsyncClient

from app.config import settings

logger = logging.getLogger(__name__)

# ── PCM chunk size for file streaming (bytes) ──────────────────────
PCM_CHUNK_SIZE = 6400  # 200ms of 16kHz 16bit mono (16000 * 2 * 0.2)


# ── Real-time WebSocket ASR (Paraformer) ───────────────────────────

class QwenRealtimeASR:
    """Connects to DashScope Paraformer real-time ASR via WebSocket.

    Protocol: binary PCM 16kHz 16bit mono → JSON results returned.
    Mirrors the XunfeiASR relay pattern so the frontend WebSocket
    client doesn't need to change.
    """

    WS_URL = "wss://dashscope.aliyuncs.com/api-ws/v1/realtime"

    def __init__(self, model: str | None = None):
        self.api_key = settings.qwen_api_key or settings.deepseek_api_key
        self.model = model or settings.qwen_asr_model

    def _ws_url(self) -> str:
        return f"{self.WS_URL}?model={self.model}"

    async def relay(self, client_ws, on_end_callback=None):
        """Bidirectional relay between browser client and Qwen Paraformer.

        - Receives binary PCM frames from client_ws → forwards to Qwen
        - Receives JSON results from Qwen → forwards to client_ws
        - Calls on_end_callback(transcript_text) when session completes
        """
        if not self.api_key:
            await client_ws.send_text(json.dumps({
                "type": "error",
                "message": "Qwen API key not configured. Set QWEN_API_KEY in .env"
            }))
            return

        url = self._ws_url()
        full_transcript: list[str] = []

        try:
            async with websockets.connect(
                url,
                additional_headers={"Authorization": f"Bearer {self.api_key}"},
                ping_interval=30,
            ) as qwen_ws:
                # Send start message with audio format config
                await qwen_ws.send(json.dumps({
                    "header": {"task": "asr", "action": "start"},
                    "payload": {"format": "pcm", "sample_rate": 16000},
                }))

                async def client_to_qwen():
                    try:
                        while True:
                            data = await client_ws.receive()
                            if data["type"] == "websocket.disconnect":
                                break
                            if "bytes" in data:
                                await qwen_ws.send(data["bytes"])
                            elif "text" in data:
                                msg = json.loads(data["text"])
                                if msg.get("type") == "end":
                                    await qwen_ws.send(json.dumps({
                                        "header": {"task": "asr", "action": "finish"}
                                    }))
                                    break
                    except Exception:
                        logger.debug("WebSocket client-to-qwen relay interrupted", exc_info=True)

                async def qwen_to_client():
                    nonlocal full_transcript
                    try:
                        async for msg_text in qwen_ws:
                            await client_ws.send_text(msg_text)
                            try:
                                data = json.loads(msg_text)
                                text = (
                                    data.get("payload", {}).get("result", "")
                                    or data.get("text", "")
                                )
                                if text:
                                    full_transcript.append(text)
                            except Exception:
                                logger.debug("Failed to parse Qwen ASR message", exc_info=True)
                    except Exception:
                        logger.debug("WebSocket qwen-to-client relay interrupted", exc_info=True)

                await asyncio.gather(client_to_qwen(), qwen_to_client())

        except websockets.exceptions.InvalidStatus as e:
            logger.error(f"Qwen ASR WebSocket failed: {e}")
            await client_ws.send_text(json.dumps({
                "type": "error",
                "message": (
                    f"Qwen ASR connection failed "
                    f"(HTTP {e.response.status_code if hasattr(e, 'response') else '?'})"
                )
            }))
        except Exception:
            logger.exception("Qwen ASR relay error")
            await client_ws.send_text(json.dumps({"type": "error", "message": "ASR service unavailable"}))

        if on_end_callback:
            await on_end_callback("".join(full_transcript))

    async def transcribe_file(self, filepath: str) -> str:
        """Transcribe an audio file via DashScope SDK Recognition (Paraformer Realtime).

        Uses the official DashScope Python SDK's Recognition class which handles
        the WebSocket protocol internally — no HTTPS URL needed.
        Converts audio to PCM 16kHz 16bit mono via ffmpeg and streams to the API.

        Returns the full transcription text (no speaker diarization).
        """
        import subprocess

        import dashscope
        from dashscope.audio.asr import Recognition, RecognitionCallback

        if not self.api_key:
            raise RuntimeError("Qwen API key not configured")

        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Audio file not found: {filepath}")

        file_size_mb = os.path.getsize(filepath) / (1024 * 1024)
        logger.info(f"ASR transcribe: {filepath} ({file_size_mb:.1f}MB)")

        # ffmpeg: convert any audio format → raw PCM s16le 16kHz mono
        proc = subprocess.run(
            [
                "ffmpeg", "-i", filepath,
                "-f", "s16le", "-acodec", "pcm_s16le",
                "-ar", "16000", "-ac", "1",
                "-loglevel", "error",
                "pipe:1",
            ],
            capture_output=True,
        )
        if proc.returncode != 0:
            stderr = proc.stderr.decode("utf-8", errors="replace")[:200]
            raise RuntimeError(f"ffmpeg conversion failed: {stderr}")

        pcm_data = proc.stdout
        duration_s = len(pcm_data) / 32000
        logger.info(f"PCM: {len(pcm_data)} bytes ({duration_s:.1f}s)")

        # Use asyncio Queue to bridge sync callback → async
        result_queue: asyncio.Queue[tuple[str, object]] = asyncio.Queue()

        class _ASRCallback(RecognitionCallback):
            def on_event(self, result):
                try:
                    result_queue.put_nowait(("event", result))
                except Exception:
                    logger.warning("ASR callback on_event failed to enqueue", exc_info=True)

            def on_error(self, result):
                try:
                    result_queue.put_nowait(("error", result))
                except Exception:
                    logger.warning("ASR callback on_error failed to enqueue", exc_info=True)

            def on_close(self):
                try:
                    result_queue.put_nowait(("close", None))
                except Exception:
                    logger.warning("ASR callback on_close failed to enqueue", exc_info=True)

            def on_open(self):
                pass  # Nothing needed

        dashscope.api_key = self.api_key

        def _run_recognition():
            recognition = Recognition(
                model=self.model,
                format="pcm",
                sample_rate=16000,
                callback=_ASRCallback(),
            )
            recognition.start()
            try:
                for offset in range(0, len(pcm_data), PCM_CHUNK_SIZE):
                    chunk = pcm_data[offset:offset + PCM_CHUNK_SIZE]
                    if chunk:
                        recognition.send_audio_frame(chunk)
            finally:
                recognition.stop()

        # Run blocking SDK in thread, collect results via async queue
        task = asyncio.create_task(asyncio.to_thread(_run_recognition))

        sentences: list[str] = []
        last_text = ""

        while True:
            try:
                msg_type, payload = await asyncio.wait_for(
                    result_queue.get(), timeout=120
                )
            except asyncio.TimeoutError:
                logger.warning("ASR: timeout waiting for results")
                break

            if msg_type == "close":
                if last_text:
                    sentences.append(last_text)
                break
            elif msg_type == "error":
                logger.error("ASR callback error: payload_type=%s", type(payload).__name__)
            elif msg_type == "event":
                output = payload.get("output", {})
                sentence = output.get("sentence", {})
                if isinstance(sentence, dict):
                    text = sentence.get("text", "")
                    end_time = sentence.get("end_time", None)
                    if text:
                        last_text = text
                    if end_time is not None and last_text:
                        sentences.append(last_text)
                        last_text = ""

        await task
        transcript = "".join(sentences)
        logger.info(f"ASR complete: {len(transcript)} chars, {len(sentences)} sentences")
        return transcript


# ── File Transcription (Qwen3-ASR-Filetrans) ───────────────────────

class QwenFileTrans:
    """Async file transcription via Qwen3-ASR-Filetrans REST API.

    Supports: WAV, MP3, M4A, OGG, FLAC, MP4, MOV (up to 2GB, 12h).
    Returns: transcript with optional speaker diarization and timestamps.
    """

    API_URL = "https://dashscope.aliyuncs.com/api/v1/services/audio/asr/transcription"

    def __init__(self, model: str | None = None):
        self.api_key = settings.qwen_api_key or settings.deepseek_api_key
        self.model = model or settings.qwen_filetrans_model
        self._client: AsyncClient | None = None

    async def _get_client(self) -> AsyncClient:
        if self._client is None:
            self._client = AsyncClient(timeout=30)
        return self._client

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    async def submit(self, file_url: str, language: str = "zh") -> str:
        """Submit an audio file for transcription. Returns task_id for polling."""
        client = await self._get_client()
        resp = await client.post(
            self.API_URL,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "X-DashScope-Async": "enable",
            },
            json={
                "model": self.model,
                "input": {"file_urls": [file_url]},
                "parameters": {
                    "language": language,
                    "speaker_diarization": True,
                },
            },
        )
        resp.raise_for_status()
        data = resp.json()
        task_id = data.get("output", {}).get("task_id", "")
        if not task_id:
            raise RuntimeError(f"No task_id in response: {data}")
        logger.info(f"FileTrans submitted: task_id={task_id}")
        return task_id

    async def poll(self, task_id: str, max_wait_s: int = 1800, interval_s: int = 5) -> dict:
        """Poll for transcription completion. Returns full result dict.

        Result includes:
        - transcription: full text
        - sentences: list of {text, begin_time, end_time, speaker_id}
        - task_status: SUCCEEDED | FAILED | RUNNING
        """
        client = await self._get_client()
        deadline = time.time() + max_wait_s

        while time.time() < deadline:
            resp = await client.get(
                f"{self.API_URL}/{task_id}",
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            resp.raise_for_status()
            data = resp.json()
            status = data.get("output", {}).get("task_status", "RUNNING")

            if status == "SUCCEEDED":
                return data["output"]
            elif status == "FAILED":
                msg = data.get("output", {}).get("message", "unknown error")
                raise RuntimeError(f"Transcription failed: {msg}")

            await asyncio.sleep(interval_s)

        raise TimeoutError(f"Transcription timed out after {max_wait_s}s")


# Singleton
qwen_filetrans = QwenFileTrans()
