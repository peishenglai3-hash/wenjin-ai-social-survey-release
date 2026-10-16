"""
Analytics service — lightweight telemetry writes to SQLite.

Usage:
  from app.services.analytics_service import AnalyticsService
  svc = AnalyticsService(db_session)
  await svc.log_event("page_view", {"page": "literature"}, user_id=1, session_id="abc")
  stats = await svc.get_stats(days=30)
"""
import json
import logging
import math
from datetime import datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analytics import AnalyticsEvent

logger = logging.getLogger(__name__)

_SAFE_PROPERTY_KEYS = frozenset({
    "page", "url", "query_length", "filter_keys", "result_count",
    "mode", "feature", "status", "source", "duration_ms",
})
_SAFE_FILTER_KEYS = frozenset({"langPref", "methodFilter", "yearFrom", "yearTo", "method"})


def _sanitize_properties(properties: object) -> dict:
    """Keep analytics metadata bounded and reject arbitrary user content."""
    if not isinstance(properties, dict):
        return {}
    safe: dict = {}
    for raw_key, value in list(properties.items())[:20]:
        key = str(raw_key)
        if key not in _SAFE_PROPERTY_KEYS:
            continue
        if key == "filter_keys":
            if isinstance(value, list):
                safe[key] = [
                    item for item in value
                    if isinstance(item, str) and item in _SAFE_FILTER_KEYS
                ][:10]
            continue
        if isinstance(value, bool):
            safe[key] = value
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            number = float(value)
            if math.isfinite(number):
                safe[key] = max(-100_000, min(100_000, int(number)))
        elif isinstance(value, str):
            safe[key] = value.strip()[:120]
    return safe


class AnalyticsService:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def log_event(
        self,
        event_name: str,
        properties: dict | None = None,
        user_id: int | None = None,
        session_id: str | None = None,
    ) -> None:
        """Persist a single analytics event to the database."""
        try:
            record = AnalyticsEvent(
                event_name=event_name,
                properties=json.dumps(_sanitize_properties(properties), ensure_ascii=False),
                user_id=user_id,
                session_id=session_id,
            )
            self._db.add(record)
            await self._db.commit()
        except Exception:
            logger.error("Failed to log analytics event '%s'", event_name, exc_info=True)
            await self._db.rollback()

    async def log_events_batch(
        self,
        events: list[dict],
    ) -> dict[str, int]:
        """Persist a batch of events. Returns {accepted, rejected}."""
        accepted = 0
        rejected = 0
        for evt in events:
            try:
                record = AnalyticsEvent(
                    event_name=evt.get("event_name", "unknown"),
                    properties=json.dumps(
                        _sanitize_properties(evt.get("properties", {})), ensure_ascii=False
                    ),
                    user_id=evt.get("user_id"),
                    session_id=evt.get("session_id"),
                )
                self._db.add(record)
                accepted += 1
            except Exception:
                logger.error(
                    "Rejected malformed analytics event: %s",
                    evt.get("event_name", "?"),
                    exc_info=True,
                )
                rejected += 1
        try:
            await self._db.commit()
        except Exception:
            logger.error("Failed to commit analytics batch", exc_info=True)
            await self._db.rollback()
            rejected += accepted
            accepted = 0
        return {"accepted": accepted, "rejected": rejected}

    async def get_stats(self, days: int = 30) -> dict:
        """Return aggregate analytics statistics for the given lookback window."""
        since = datetime.utcnow() - timedelta(days=days)

        total_result = await self._db.execute(
            select(func.count(AnalyticsEvent.id)).where(
                AnalyticsEvent.created_at >= since
            )
        )
        total = total_result.scalar() or 0

        top_events_result = await self._db.execute(
            select(
                AnalyticsEvent.event_name,
                func.count(AnalyticsEvent.id).label("cnt"),
            )
            .where(AnalyticsEvent.created_at >= since)
            .group_by(AnalyticsEvent.event_name)
            .order_by(text("cnt DESC"))
            .limit(20)
        )
        top_events = [
            {"event_name": row[0], "count": row[1]}
            for row in top_events_result.all()
        ]

        unique_sessions_result = await self._db.execute(
            select(func.count(func.distinct(AnalyticsEvent.session_id))).where(
                AnalyticsEvent.created_at >= since
            )
        )
        unique_sessions = unique_sessions_result.scalar() or 0

        daily_result = await self._db.execute(
            select(
                func.date(AnalyticsEvent.created_at).label("day"),
                func.count(AnalyticsEvent.id).label("cnt"),
            )
            .where(AnalyticsEvent.created_at >= since)
            .group_by(text("day"))
            .order_by(text("day"))
        )
        daily = [
            {"date": str(row[0]), "count": row[1]}
            for row in daily_result.all()
        ]

        return {
            "total_events": total,
            "unique_sessions": unique_sessions,
            "days": days,
            "top_events": top_events,
            "daily": daily,
        }
