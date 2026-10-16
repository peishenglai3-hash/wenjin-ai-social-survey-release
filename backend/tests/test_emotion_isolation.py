"""Regression tests for per-connection emotion state and timeline ownership."""

from app.services.emotion_tracker import (
    EmotionTimeline,
    EmotionTimelineStore,
    EmotionTracker,
)


def test_trackers_keep_state_per_connection() -> None:
    first = EmotionTracker(sample_interval_s=0)
    second = EmotionTracker(sample_interval_s=0)
    first.start_session("first")
    second.start_session("second")

    first.feed_facial({"expression": "happy", "engagement": 0.9})

    assert first.get_timeline().samples
    assert second.get_timeline().samples == []


def test_timeline_store_is_owner_scoped() -> None:
    store = EmotionTimelineStore(ttl_seconds=60)
    timeline = EmotionTimeline(overall_mood="happy")
    store.put("session-a", owner_id=10, timeline=timeline)

    assert store.get("session-a", owner_id=10).overall_mood == "happy"
    assert store.get("session-a", owner_id=11) is None
