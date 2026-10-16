"""Small, cursor-free pagination helpers for bounded collaboration lists."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, TypeVar


T = TypeVar("T")


def take_page(items: Sequence[T], *, limit: int, offset: int) -> tuple[list[T], dict[str, Any]]:
    """Trim a limit+1 query result and return stable page metadata."""
    has_more = len(items) > limit
    page = list(items[:limit])
    return page, {
        "limit": limit,
        "offset": offset,
        "has_more": has_more,
        "next_offset": offset + limit if has_more else None,
    }
