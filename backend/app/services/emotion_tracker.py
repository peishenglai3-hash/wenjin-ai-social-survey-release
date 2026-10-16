"""
Real-time Emotion Tracker — multi-modal emotion detection during interviews.
Fuses: voice acoustics (emotion2vec+) + semantic sentiment (LLM) + facial signals (MediaPipe).
Outputs real-time emotion stream consumable by the interviewer HUD.
"""

from __future__ import annotations
import asyncio, json, logging, time
from copy import deepcopy
from collections import deque
from dataclasses import dataclass, field
from threading import RLock
from typing import Optional
from app.config import settings

logger = logging.getLogger(__name__)

@dataclass
class EmotionSample:
    timestamp_ms: int
    voice_emotion: str = "neutral"
    voice_confidence: float = 0.0
    semantic_sentiment: str = "neutral"
    semantic_confidence: float = 0.0
    speech_rate_wpm: float = 0.0
    pause_ratio: float = 0.0
    volume_peak: float = 0.0
    # ── Facial signals (from CameraCapture / MediaPipe) ──
    facial_engagement: float = 0.0      # 0–1 overall engagement
    facial_expression: str = "neutral"  # happy|surprised|concentrating|tired|uncertain|neutral
    facial_head_yaw: float = 0.0        # head turn degrees (±)
    facial_head_pitch: float = 0.0      # head tilt degrees (±)
    facial_available: bool = False      # True if facial data was received this sample
    fused_emotion: str = "neutral"
    fused_intensity: float = 0.0

@dataclass
class EmotionTimeline:
    samples: list = field(default_factory=list)
    overall_mood: str = "neutral"
    mood_stability: float = 0.0
    emotional_peaks: list = field(default_factory=list)
    summary: str = ""

@dataclass
class EmotionAlert:
    type: str = "info"
    message: str = ""
    suggested_action: str = ""
    urgency: float = 0.0


class EmotionTimelineStore:
    """Bounded, owner-scoped store for completed WebSocket timelines.

    Trackers themselves are always per WebSocket connection.  This small
    store only keeps completed timelines long enough for the existing HTTP
    retrieval endpoint to remain useful; it never exposes one user's
    timeline to another user.
    """

    def __init__(self, max_entries: int = 256, ttl_seconds: int = 3600):
        self.max_entries = max_entries
        self.ttl_seconds = ttl_seconds
        self._entries: dict[str, tuple[int, float, EmotionTimeline]] = {}
        self._lock = RLock()

    def put(self, session_id: str, owner_id: int, timeline: EmotionTimeline) -> None:
        now = time.time()
        with self._lock:
            self._prune(now)
            self._entries[session_id] = (owner_id, now, deepcopy(timeline))
            while len(self._entries) > self.max_entries:
                oldest = min(self._entries, key=lambda key: self._entries[key][1])
                self._entries.pop(oldest, None)

    def get(self, session_id: str, owner_id: int) -> EmotionTimeline | None:
        now = time.time()
        with self._lock:
            self._prune(now)
            entry = self._entries.get(session_id)
            if entry is None or entry[0] != owner_id:
                return None
            return deepcopy(entry[2])

    def _prune(self, now: float) -> None:
        expired = [
            session_id
            for session_id, (_, created_at, _) in self._entries.items()
            if now - created_at > self.ttl_seconds
        ]
        for session_id in expired:
            self._entries.pop(session_id, None)

class EmotionTracker:
    """Real-time multi-modal emotion tracker for interview scenarios.
    Fuses voice acoustics + semantic sentiment + para-linguistic features.
    """

    ALERT_TRIGGERS = {
        ("sad", 0.6): EmotionAlert(type="tip", urgency=0.5,
            message="受访者表现出悲伤情绪",
            suggested_action="可以表达共情，适当放慢节奏，给受访者空间"),
        ("angry", 0.7): EmotionAlert(type="warning", urgency=0.7,
            message="受访者情绪激动/愤怒",
            suggested_action="避免追问争议点，先接纳情绪，等对方平静后再深入"),
        ("happy", 0.5): EmotionAlert(type="info", urgency=0.2,
            message="受访者情绪积极开放",
            suggested_action="这是深入追问的好时机，受访者更愿意分享"),
        # ── Bimodal alerts (facial + voice) ──
        ("social_desirability", 0.55): EmotionAlert(type="warning", urgency=0.55,
            message="⚠️ 表情-语音不一致：受访者面部微笑但语音情绪偏负面",
            suggested_action="可能存在社会期望偏差，尝试换角度追问或使用投射性问题"),
        ("fatigue", 0.5): EmotionAlert(type="tip", urgency=0.4,
            message="受访者表现出疲劳迹象（眨眼增多/头部偏移）",
            suggested_action="考虑暂停休息或切换到轻松话题，注意受访者状态"),
        ("disengagement", 0.6): EmotionAlert(type="warning", urgency=0.65,
            message="受访者注意力下降（头部大幅偏转/专注度低）",
            suggested_action="重新建立互动，确认受访者是否愿意继续，或调整访谈节奏"),
    }

    def __init__(self, sample_interval_s: float = 5.0, user_id: int | None = None):
        self.sample_interval_s = sample_interval_s
        self.user_id = user_id
        self._samples: deque = deque(maxlen=720)
        self._session_id = ""
        self._started_at = 0.0
        self._last_sample_at = 0.0
        self._transcript_buffer = ""

    def start_session(self, session_id: str) -> None:
        self._session_id = session_id
        self._started_at = time.time()
        self._last_sample_at = self._started_at
        self._samples.clear()
        self._transcript_buffer = ""

    def end_session(self) -> EmotionTimeline:
        return self.get_timeline()

    async def feed_audio(self, pcm_bytes: bytes) -> Optional[EmotionSample]:
        now = time.time()
        if now - self._last_sample_at < self.sample_interval_s:
            return None
        sample = EmotionSample(timestamp_ms=int((now - self._started_at) * 1000))
        sample.volume_peak = self._estimate_volume(pcm_bytes)
        sample.fused_emotion = self._fuse(sample)
        sample.fused_intensity = self._intensity(sample)
        self._samples.append(sample)
        self._last_sample_at = now
        return sample

    async def feed_transcript(self, text: str) -> None:
        self._transcript_buffer = (self._transcript_buffer + "\n" + text)[-2000:]
        if self._samples:
            latest = self._samples[-1]
            sentiment = await self._llm_sentiment(text)
            if sentiment:
                latest.semantic_sentiment = sentiment.get("label", "neutral")
                latest.semantic_confidence = sentiment.get("confidence", 0.0)
                latest.fused_emotion = self._fuse(latest)
                latest.fused_intensity = self._intensity(latest)

    def feed_facial(self, facial_data: dict) -> Optional[EmotionSample]:
        """Feed facial emotion signals from CameraCapture/MediaPipe into the tracker.

        Args:
            facial_data: dict with keys matching FacialSignal TS interface:
                engagement, expression, head_yaw, head_pitch, ear_left, ear_right,
                mouth_curve, brow_lift, head_roll, timestamp

        Returns the updated EmotionSample, or None if within sample interval.
        """
        now = time.time()
        timestamp_ms = facial_data.get("timestamp", int(now * 1000))

        # Get or create sample for this time window
        if self._samples and (now - self._last_sample_at < self.sample_interval_s):
            sample = self._samples[-1]
        else:
            sample = EmotionSample(timestamp_ms=timestamp_ms)
            self._samples.append(sample)
            self._last_sample_at = now

        # Store facial data
        sample.facial_engagement = float(facial_data.get("engagement", 0.0))
        sample.facial_expression = str(facial_data.get("expression", "neutral"))
        sample.facial_head_yaw = float(facial_data.get("head_yaw", 0.0))
        sample.facial_head_pitch = float(facial_data.get("head_pitch", 0.0))
        sample.facial_available = True

        # Re-fuse with new facial data
        sample.fused_emotion = self._fuse(sample)
        sample.fused_intensity = self._intensity(sample)

        return sample

    def current_alert(self) -> Optional[EmotionAlert]:
        if not self._samples:
            return None
        latest = self._samples[-1]
        for (emotion, threshold), alert in self.ALERT_TRIGGERS.items():
            if latest.fused_emotion == emotion and latest.fused_intensity >= threshold:
                return alert
        return None

    def get_timeline(self) -> EmotionTimeline:
        samples = list(self._samples)
        if not samples:
            return EmotionTimeline()
        mood_counts: dict = {}
        for s in samples:
            mood_counts[s.fused_emotion] = mood_counts.get(s.fused_emotion, 0) + 1
        overall_mood = max(mood_counts, key=mood_counts.get) if mood_counts else "neutral"
        changes = sum(1 for i in range(1, len(samples)) if samples[i].fused_emotion != samples[i-1].fused_emotion)
        stability = 1.0 - (changes / max(len(samples)-1, 1))
        sorted_samples = sorted(samples, key=lambda s: s.fused_intensity, reverse=True)
        peaks = [{"timestamp_ms": s.timestamp_ms, "emotion": s.fused_emotion, "intensity": round(s.fused_intensity,2)} for s in sorted_samples[:5]]
        return EmotionTimeline(samples=samples, overall_mood=overall_mood, mood_stability=round(stability, 2), emotional_peaks=peaks)

    def get_recent_emotion(self, window_s: float = 30.0) -> str:
        if not self._samples:
            return "neutral"
        now = time.time()
        cutoff = int((now - self._started_at - window_s) * 1000)
        recent = [s for s in self._samples if s.timestamp_ms >= cutoff]
        if not recent:
            return self._samples[-1].fused_emotion
        counts: dict = {}
        for s in recent:
            counts[s.fused_emotion] = counts.get(s.fused_emotion, 0) + 1
        return max(counts, key=counts.get)

    async def _llm_sentiment(self, text: str) -> Optional[dict]:
        """Semantic sentiment via Volcano Doubao (primary) or DeepSeek (fallback)."""
        if not text.strip() or len(text.strip()) < 10:
            return None
        try:
            # Primary: Volcano Engine Doubao (best Chinese emotion understanding)
            if settings.volcano_api_key and settings.volcano_emotion_enabled:
                from app.services.volcano_emotion import volcano_emotion
                result = await volcano_emotion.analyze_emotion(
                    text, speaker_role="respondent"
                )
                if result.confidence > 0.1:
                    return {
                        "label": result.primary_emotion,
                        "confidence": result.confidence,
                    }

            # Fallback: DeepSeek
            from app.services.ai import AIService
            ai = AIService(api_key=settings.deepseek_api_key, base_url=settings.deepseek_base_url, model="deepseek-v4-flash")
            prompt = f'分析以下受访者发言的情感倾向，仅输出JSON: {{"label": "positive|negative|neutral|mixed", "confidence": 0.0-1.0}}\n\n"{text[:500]}"'
            messages = [{"role":"system","content":"你是一个情感分析器。只输出JSON。"}, {"role":"user","content":prompt}]
            result = await ai.chat(
                messages,
                temperature=0.1,
                max_tokens=128,
                task="hints",
                user_id=self.user_id,
            )
            return json.loads(result.strip())
        except Exception:
            logger.warning("Emotion analysis failed", exc_info=True)
            return None

    @staticmethod
    def _estimate_volume(pcm_bytes: bytes) -> float:
        try:
            import struct
            samples = struct.unpack(f"{len(pcm_bytes)//2}h", pcm_bytes)
            if not samples: return 0.0
            return min(max(abs(s) for s in samples) / 32768.0, 1.0)
        except Exception:
            logger.debug("Volume estimation failed", exc_info=True)
            return 0.0

    @staticmethod
    def _fuse(sample: EmotionSample) -> str:
        """Trimodal fusion: voice(0.35) + semantic(0.35) + facial(0.30).

        Priority: semantic > facial > voice for emotion label,
        but facial engagement can override when voice is neutral.
        """
        # Collect weighted votes for each emotion
        votes: dict[str, float] = {}

        # Voice vote (weight 0.35)
        if sample.voice_confidence > 0.3:
            votes[sample.voice_emotion] = votes.get(sample.voice_emotion, 0.0) + 0.35 * sample.voice_confidence

        # Semantic vote (weight 0.35)
        if sample.semantic_confidence > 0.3:
            mapping = {"positive": "happy", "negative": "sad", "mixed": "neutral"}
            sem_emotion = mapping.get(sample.semantic_sentiment, "neutral")
            votes[sem_emotion] = votes.get(sem_emotion, 0.0) + 0.35 * sample.semantic_confidence

        # Facial vote (weight 0.30)
        if sample.facial_available:
            facial_emotion = sample.facial_expression
            # Map facial expressions to emotion labels
            facial_map = {
                "happy": "happy", "surprised": "surprised",
                "concentrating": "neutral", "tired": "sad",
                "uncertain": "sad", "neutral": "neutral",
            }
            mapped = facial_map.get(facial_emotion, "neutral")
            # Weight by engagement: higher engagement = more reliable facial signal
            facial_weight = 0.30 * (0.5 + 0.5 * sample.facial_engagement)
            votes[mapped] = votes.get(mapped, 0.0) + facial_weight

            # Facial-voice mismatch detection: smiling face + negative voice → social desirability
            if (facial_emotion == "happy" and sample.facial_engagement > 0.5 and
                (sample.voice_emotion in ("sad", "angry") or sample.semantic_sentiment == "negative")):
                votes["social_desirability"] = votes.get("social_desirability", 0.0) + 0.5

            # Fatigue detection: low engagement + tired expression
            if (facial_emotion == "tired" and sample.facial_engagement < 0.4):
                votes["fatigue"] = votes.get("fatigue", 0.0) + 0.4

            # Disengagement: low engagement + large head turn
            if (sample.facial_engagement < 0.35 and abs(sample.facial_head_yaw) > 20):
                votes["disengagement"] = votes.get("disengagement", 0.0) + 0.5

        if not votes:
            return "neutral"

        # Return emotion with highest weighted vote
        return max(votes, key=votes.get)

    @staticmethod
    def _intensity(sample: EmotionSample) -> float:
        intensity = 0.3
        if sample.voice_emotion in ("angry","sad"): intensity += 0.2
        if sample.semantic_sentiment in ("negative","mixed"): intensity += 0.15
        if sample.volume_peak > 0.7: intensity += 0.15
        if sample.voice_confidence > 0.7: intensity += 0.1
        # Facial contributions
        if sample.facial_available:
            if sample.facial_expression in ("surprised", "happy"): intensity += 0.1
            if sample.facial_engagement < 0.35: intensity += 0.1  # low engagement is notable
            if abs(sample.facial_head_yaw) > 20: intensity += 0.05  # looking away
        return min(intensity, 1.0)

emotion_timeline_store = EmotionTimelineStore()
