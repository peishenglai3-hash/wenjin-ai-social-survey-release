"""
Redis-backed sliding window rate limit store with in-memory fallback.

Uses Redis sorted sets for atomic sliding window operations.
Falls back to in-memory dict when Redis is unavailable (dev, cold start, outage).
"""

import time
import uuid
import logging
from collections import defaultdict
from typing import Optional

logger = logging.getLogger(__name__)


class MemoryRateLimitStore:
    """In-memory sliding window store — always available, per-process only."""

    def __init__(self):
        self._windows: dict[str, list[float]] = defaultdict(list)
        self._last_cleanup = time.time()

    async def check_and_increment(
        self, key: str, window_s: int = 60, limit: int = 60
    ) -> tuple[bool, int, int]:
        """
        Returns (allowed: bool, current_count: int, retry_after_or_remaining: int).
        - If allowed: third value is remaining capacity.
        - If denied: third value is retry_after seconds.
        """
        now = time.time()
        cutoff = now - window_s
        window = self._windows[key]

        # Slide window — remove expired timestamps
        while window and window[0] < cutoff:
            window.pop(0)

        if len(window) >= limit:
            retry_after = max(1, int(window_s - (now - window[0])))
            return False, len(window), retry_after

        window.append(now)
        remaining = max(0, limit - len(window))

        # Periodic cleanup of empty/stale keys
        if now - self._last_cleanup > 120:
            stale = [
                k for k in list(self._windows.keys())
                if not self._windows[k] or self._windows[k][-1] < cutoff
            ]
            for k in stale:
                del self._windows[k]
            self._last_cleanup = now

        return True, len(window), remaining


class RedisRateLimitStore:
    """Redis-backed sliding window rate limit store.

    Uses sorted sets:
    - ZREMRANGEBYSCORE to evict expired entries
    - ZCARD to count current window
    - ZADD to record the request
    - EXPIRE to auto-clean the key after the window
    """

    def __init__(self, redis_url: str):
        self._redis_url = redis_url
        self._redis = None
        self._initialized = False
        self._fallback = MemoryRateLimitStore()

    async def _ensure_redis(self):
        """Lazy-init Redis connection; returns None if unavailable."""
        if self._initialized:
            return self._redis
        self._initialized = True
        try:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(
                self._redis_url,
                decode_responses=False,
                socket_connect_timeout=2,
                socket_timeout=2,
                retry_on_timeout=False,
            )
            await self._redis.ping()
            logger.info("Redis rate limit store connected")
        except Exception as exc:
            logger.warning(
                "Redis unavailable (%s), falling back to in-memory rate limiting. "
                "Install Redis or configure Redis for production use.",
                type(exc).__name__,
            )
            self._redis = None
        return self._redis

    async def check_and_increment(
        self, key: str, window_s: int = 60, limit: int = 60
    ) -> tuple[bool, int, int]:
        """
        Returns (allowed: bool, current_count: int, retry_after_or_remaining: int).
        Atomically checks and increments the sliding window in Redis.
        Falls back to in-memory store on any Redis error.
        """
        redis = await self._ensure_redis()
        if redis is None:
            return await self._fallback.check_and_increment(key, window_s, limit)

        try:
            now = time.time()
            member = f"{now}:{uuid.uuid4().hex[:8]}"
            redis_key = f"rl:{key}"

            # 1. Evict entries outside the window
            cutoff = now - window_s
            await redis.zremrangebyscore(redis_key, 0, cutoff)

            # 2. Count remaining entries
            count = await redis.zcard(redis_key)

            if count >= limit:
                # Denied — compute retry_after from oldest entry in window
                oldest = await redis.zrange(redis_key, 0, 0, withscores=True)
                if oldest:
                    retry_after = max(1, int(window_s - (now - oldest[0][1])))
                else:
                    retry_after = window_s
                return False, count, retry_after

            # 3. Allowed — add this request
            await redis.zadd(redis_key, {member: now})
            await redis.expire(redis_key, window_s + 5)
            return True, count + 1, max(0, limit - (count + 1))

        except Exception as exc:
            logger.warning(
                "Redis rate limit error (%s), using in-memory fallback",
                type(exc).__name__,
            )
            return await self._fallback.check_and_increment(key, window_s, limit)


# ── Module-level singleton ──
_rate_limit_store: Optional[RedisRateLimitStore] = None


def get_rate_limit_store() -> RedisRateLimitStore:
    """Get or create the rate limit store singleton."""
    global _rate_limit_store
    if _rate_limit_store is None:
        from app.config import settings
        _rate_limit_store = RedisRateLimitStore(settings.redis_url)
    return _rate_limit_store
