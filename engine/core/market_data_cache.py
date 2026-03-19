"""In-memory cache with TTL to avoid duplicate API calls."""

from __future__ import annotations

import time
from typing import Any, Optional


class _CacheEntry:
    __slots__ = ("value", "expires_at")

    def __init__(self, value: Any, ttl_sec: float) -> None:
        self.value = value
        self.expires_at = time.monotonic() + ttl_sec


class MarketDataCache:
    """Simple TTL-based in-memory cache (thread-unsafe, fine for asyncio)."""

    def __init__(self, ttl_sec: float = 10.0) -> None:
        self._ttl = ttl_sec
        self._store: dict[str, _CacheEntry] = {}

    def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if entry is None:
            return None
        if time.monotonic() > entry.expires_at:
            del self._store[key]
            return None
        return entry.value

    def set(self, key: str, value: Any, ttl_sec: Optional[float] = None) -> None:
        self._store[key] = _CacheEntry(value, ttl_sec if ttl_sec is not None else self._ttl)

    def invalidate(self, key: str) -> None:
        self._store.pop(key, None)

    def invalidate_prefix(self, prefix: str) -> int:
        """Remove all entries whose key starts with *prefix*. Returns count removed."""
        keys = [k for k in self._store if k.startswith(prefix)]
        for k in keys:
            del self._store[k]
        return len(keys)

    def clear(self) -> None:
        self._store.clear()

    def cleanup(self) -> int:
        """Evict expired entries. Returns count removed."""
        now = time.monotonic()
        expired = [k for k, v in self._store.items() if now > v.expires_at]
        for k in expired:
            del self._store[k]
        return len(expired)

    @property
    def size(self) -> int:
        return len(self._store)
