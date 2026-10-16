"""
Real-time Interview Pipeline — WebSocket orchestrator.
Combines: SpeechEngine + EmotionTracker + AI Coach + Facial Signals.
Streams: transcript, emotion alerts, coach hints, 2-min summaries.
Supports mixed messages: binary PCM (audio) + JSON text (facial signals).
"""

from __future__ import annotations
import asyncio, json, logging, time
import uuid
from typing import Optional
from fastapi import WebSocket, WebSocketDisconnect
from app.config import settings
from app.services.emotion_tracker import EmotionTracker, EmotionAlert, emotion_timeline_store

logger = logging.getLogger(__name__)

SUMMARY_INTERVAL_S = 120
HINT_INTERVAL_S = 15
EMOTION_SAMPLE_INTERVAL_S = 5.0
MAX_AUDIO_FRAME_BYTES = 256 * 1024
MAX_TEXT_FRAME_BYTES = 32 * 1024
MAX_MESSAGES_PER_MINUTE = 600

class RealtimePipeline:
    """WebSocket-based real-time interview pipeline.
    Client sends binary PCM frames (audio) + JSON text (facial signals);
    server returns JSON with transcript, emotion, hints, summaries.
    """

    def __init__(self):
        self.emotion: Optional[EmotionTracker] = None
        self._session_id = ""
        self._scenario = "community_interview"
        self._theme = "academic"
        self._phase = "opening"
        self._full_transcript: list = []
        self._transcript_since_summary: list = []
        self._transcript_since_hint: list = []
        self._current_speaker: str = "interviewer"  # "interviewer" | "respondent"
        self._started_at = 0.0
        self._last_summary_at = 0.0
        self._last_hint_at = 0.0
        self._owner_id: int | None = None

    async def handle(self, ws: WebSocket, session_id: str = "", scenario: str = "community_interview",
                     theme: str = "academic", phase: str = "opening", owner_id: int | None = None) -> None:
        self._session_id = session_id[:64] or f"session_{uuid.uuid4().hex[:12]}"
        self._owner_id = owner_id
        self._scenario = scenario; self._theme = theme; self._phase = phase
        self._started_at = time.time()
        self._last_summary_at = self._started_at; self._last_hint_at = self._started_at
        self._full_transcript.clear(); self._transcript_since_summary.clear(); self._transcript_since_hint.clear()

        self.emotion = EmotionTracker(
            sample_interval_s=EMOTION_SAMPLE_INTERVAL_S,
            user_id=owner_id,
        )
        self.emotion.start_session(self._session_id)

        await ws.send_json({"type":"session_started","session_id":self._session_id,"scenario":self._scenario,"phase":self._phase,"timestamp_ms":0})

        summary_task = asyncio.create_task(self._summary_loop(ws))
        hint_task = asyncio.create_task(self._hint_loop(ws))

        try:
            await self._message_loop(ws)
        except WebSocketDisconnect:
            logger.info(f"Pipeline: client disconnected ({self._session_id})")
        except Exception:
            logger.exception("Pipeline error")
            try: await ws.send_json({"type":"error","message":"Interview pipeline unavailable"})
            except Exception:
                logger.warning("Failed to send error message to WebSocket", exc_info=True)
        finally:
            summary_task.cancel(); hint_task.cancel()
            if self.emotion:
                timeline = self.emotion.end_session()
                if owner_id is not None:
                    emotion_timeline_store.put(self._session_id, owner_id, timeline)
                try:
                    await ws.send_json({"type":"session_ended","session_id":self._session_id,
                        "duration_s":int(time.time()-self._started_at),
                        "full_transcript":"".join(self._full_transcript),
                        "emotion_timeline":{"overall_mood":timeline.overall_mood,"mood_stability":timeline.mood_stability,"emotional_peaks":timeline.emotional_peaks}})
                except Exception:
                    logger.warning("Failed to send session_ended to WebSocket", exc_info=True)

    async def _message_loop(self, ws: WebSocket) -> None:
        """Handle mixed client messages: binary PCM → ASR, text JSON → facial/control."""
        from app.services.asr_qwen import QwenRealtimeASR
        import websockets as ws_lib

        asr = QwenRealtimeASR()
        if not asr.api_key:
            await ws.send_json({"type": "error", "message": "ASR API key not configured"})
            return

        qwen_url = asr._ws_url()
        try:
            async with ws_lib.connect(
                qwen_url,
                additional_headers={"Authorization": f"Bearer {asr.api_key}"},
                ping_interval=30,
            ) as qwen_ws:
                # Start Qwen ASR session
                await qwen_ws.send(json.dumps({
                    "header": {"task": "asr", "action": "start"},
                    "payload": {"format": "pcm", "sample_rate": 16000},
                }))

                # ── Qwen → Client relay ──
                async def qwen_to_client():
                    try:
                        async for msg_text in qwen_ws:
                            await ws.send_text(msg_text)
                            try:
                                data = json.loads(msg_text)
                                text = (
                                    data.get("payload", {}).get("result", "")
                                    or data.get("text", "")
                                )
                                if text and text.strip():
                                    entry = {
                                        "speaker": self._current_speaker,
                                        "text": text.strip(),
                                        "timestamp_ms": int(time.time() * 1000),
                                    }
                                    self._full_transcript.append(entry)
                                    self._transcript_since_summary.append(text)
                                    self._transcript_since_hint.append(text)
                                    # Feed transcript to emotion tracker
                                    if self.emotion:
                                        await self.emotion.feed_transcript(text)
                            except Exception:
                                logger.debug("Failed to parse Qwen ASR message", exc_info=True)
                    except Exception:
                        logger.debug("Qwen→Client relay ended", exc_info=True)

                # ── Client → Qwen + Facial dispatch ──
                async def client_dispatch():
                    message_count = 0
                    rate_window_started = time.monotonic()
                    try:
                        while True:
                            data = await ws.receive()
                            if data["type"] == "websocket.disconnect":
                                break
                            now = time.monotonic()
                            if now - rate_window_started >= 60:
                                rate_window_started = now
                                message_count = 0
                            message_count += 1
                            if message_count > MAX_MESSAGES_PER_MINUTE:
                                await ws.send_json({"type": "error", "message": "WebSocket message rate exceeded"})
                                await ws.close(code=1013)
                                break
                            if "bytes" in data:
                                if data["bytes"] is None or len(data["bytes"]) > MAX_AUDIO_FRAME_BYTES:
                                    await ws.send_json({"type": "error", "message": "Audio frame too large"})
                                    await ws.close(code=1009)
                                    break
                                # Binary PCM audio → forward to Qwen
                                await qwen_ws.send(data["bytes"])
                                # Feed audio to emotion tracker for volume estimation
                                if self.emotion:
                                    await self.emotion.feed_audio(data["bytes"])
                            elif "text" in data:
                                if data["text"] is None or len(data["text"].encode("utf-8")) > MAX_TEXT_FRAME_BYTES:
                                    await ws.send_json({"type": "error", "message": "Text frame too large"})
                                    await ws.close(code=1009)
                                    break
                                msg = json.loads(data["text"])
                                msg_type = msg.get("type", "")
                                if msg_type == "end":
                                    await qwen_ws.send(json.dumps({
                                        "header": {"task": "asr", "action": "finish"}
                                    }))
                                    break
                                elif msg_type == "facial_signal":
                                    # Feed facial signal to emotion tracker
                                    signal = msg.get("signal", {})
                                    if self.emotion and signal:
                                        sample = self.emotion.feed_facial(signal)
                                        if sample:
                                            alert = self.emotion.current_alert()
                                            if alert:
                                                current_emotion = self.emotion.get_recent_emotion(window_s=30)
                                                await ws.send_json({
                                                    "type": "emotion_alert",
                                                    "emotion": current_emotion,
                                                    "message": alert.message,
                                                    "suggested_action": alert.suggested_action,
                                                    "urgency": alert.urgency,
                                                    "timestamp_ms": int((time.time() - self._started_at) * 1000),
                                                })
                                elif msg_type == "speaker_change":
                                    speaker = msg.get("speaker", "interviewer")
                                    if speaker in ("interviewer", "respondent"):
                                        self._current_speaker = speaker
                                        logger.debug(f"Speaker changed to: {speaker}")
                                elif msg_type == "ping":
                                    await ws.send_json({"type": "pong"})
                                else:
                                    logger.debug(f"Unknown text message type: {msg_type}")
                    except Exception:
                        logger.debug("Client dispatch ended", exc_info=True)

                await asyncio.gather(client_dispatch(), qwen_to_client())

        except ws_lib.exceptions.InvalidStatus as e:
            logger.error(f"Qwen ASR WebSocket failed: {e}")
            await ws.send_json({"type": "error", "message": f"Qwen ASR connection failed (HTTP {e.response.status_code if hasattr(e, 'response') else '?'})"})
        except Exception:
            logger.exception("Pipeline message loop error")
            await ws.send_json({"type": "error", "message": "Interview pipeline unavailable"})

    async def _summary_loop(self, ws: WebSocket) -> None:
        await asyncio.sleep(SUMMARY_INTERVAL_S)
        while True:
            try:
                recent = "".join(self._transcript_since_summary)
                if recent.strip():
                    summary = await self._generate_summary(recent)
                    await ws.send_json({"type":"summary_2min","summary":summary,"timestamp_ms":int((time.time()-self._started_at)*1000)})
                    self._transcript_since_summary.clear()
            except Exception as e: logger.warning(f"Summary failed: {e}")
            await asyncio.sleep(SUMMARY_INTERVAL_S)

    async def _hint_loop(self, ws: WebSocket) -> None:
        await asyncio.sleep(HINT_INTERVAL_S)
        while True:
            try:
                recent = "".join(self._transcript_since_hint)
                if recent.strip() and self.emotion:
                    current_emotion = self.emotion.get_recent_emotion(window_s=30)
                    alert = self.emotion.current_alert()
                    if alert:
                        await ws.send_json({"type":"emotion_alert","emotion":current_emotion,"message":alert.message,"suggested_action":alert.suggested_action,"urgency":alert.urgency,"timestamp_ms":int((time.time()-self._started_at)*1000)})
                    hints = await self._generate_hints({"transcript":recent,"scenario":self._scenario,"phase":self._phase,"theme":self._theme,"emotion":current_emotion}, alert)
                    if hints:
                        await ws.send_json({"type":"coach_hint","hints":hints,"emotion":current_emotion,"timestamp_ms":int((time.time()-self._started_at)*1000)})
                    self._transcript_since_hint.clear()
            except Exception as e: logger.warning(f"Hint failed: {e}")
            await asyncio.sleep(HINT_INTERVAL_S)

    async def _generate_summary(self, transcript: str) -> str:
        from app.services.ai import AIService
        ai = AIService(api_key=settings.deepseek_api_key, base_url=settings.deepseek_base_url, model="deepseek-v4-flash")
        prompt = f"请将以下约2分钟的访谈片段浓缩为1-2句话的要点总结：\n\n{transcript[:2000]}\n\n要求：只输出1-2句中文，包含关键信息和主题方向。"
        messages = [{"role":"system","content":"你是专业的访谈纪要助手。简洁、精准。"}, {"role":"user","content":prompt}]
        result = await ai.chat(
            messages,
            temperature=0.3,
            max_tokens=256,
            task="summarize",
            user_id=self._owner_id,
        )
        return result.strip()

    async def _generate_hints(self, payload: dict, alert: Optional[EmotionAlert]) -> list:
        """Generate coach hints via Volcano Doubao (primary) or DeepSeek (fallback)."""
        emotion = payload.get("emotion", "neutral")
        transcript = payload.get("transcript", "")
        scenario = payload.get("scenario", "community_interview")
        phase = payload.get("phase", "opening")
        emotion_context = ""
        if alert:
            emotion_context = f"\n当前受访者情绪: {emotion}。{alert.suggested_action}\n"

        # Primary: Volcano Doubao (best Chinese emotion understanding)
        if settings.volcano_api_key and settings.volcano_emotion_enabled:
            try:
                from app.services.volcano_emotion import volcano_emotion
                hint_text = await volcano_emotion.generate_hint(
                    transcript_snippet=transcript,
                    current_emotion=emotion,
                )
                if hint_text:
                    return [hint_text] if isinstance(hint_text, str) else hint_text
            except Exception as e:
                logger.warning(f"Volcano hint failed, falling back to DeepSeek: {e}")

        # Fallback: DeepSeek
        from app.services.ai import AIService
        ai = AIService(api_key=settings.deepseek_api_key, base_url=settings.deepseek_base_url, model="deepseek-v4-flash")
        prompt = f"访谈场景: {scenario}\n阶段: {phase}\n情绪: {emotion}{emotion_context}\n最近对话:\n{transcript[:1500]}\n\n作为访谈教练，提供2-3条即时建议（追问方向/话术建议）。每条20字以内。输出JSON数组: [\"建议1\",\"建议2\"]"
        messages = [{"role":"system","content":"你是田野访谈教练，提供简洁可操作的即时建议。输出纯JSON数组。"}, {"role":"user","content":prompt}]
        try:
            result = await ai.chat(
                messages,
                temperature=0.5,
                max_tokens=512,
                task="hints",
                user_id=self._owner_id,
            )
            return json.loads(result.strip())
        except Exception:
            logger.warning("Hint generation via DeepSeek fallback failed", exc_info=True)
            return []
