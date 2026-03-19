"""Fear & Greed Index fetcher with caching and DCA multiplier logic."""

from __future__ import annotations

import time
from typing import Optional

import httpx
from loguru import logger

_FNG_API = "https://api.alternative.me/fng/"
_CACHE_TTL = 3600  # 1 hour


class FearGreedFetcher:
    """Fetches and caches the Crypto Fear & Greed Index."""

    def __init__(self) -> None:
        self._cached_value: Optional[int] = None
        self._cached_history: Optional[list[dict]] = None
        self._last_fetch_ts: float = 0.0
        self._last_history_ts: float = 0.0

    # ── Public API ──────────────────────────────────────────

    async def fetch_current(self) -> int:
        """Return current Fear & Greed value (0-100). Uses 1h cache."""
        now = time.time()
        if self._cached_value is not None and (now - self._last_fetch_ts) < _CACHE_TTL:
            return self._cached_value

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(_FNG_API, params={"limit": 1, "format": "json"})
                resp.raise_for_status()
                data = resp.json()
                value = int(data["data"][0]["value"])
                self._cached_value = value
                self._last_fetch_ts = now
                logger.debug("Fear & Greed fetched: {}", value)
                return value
        except Exception as e:
            logger.warning("Fear & Greed fetch failed: {}. Using cache.", e)
            if self._cached_value is not None:
                return self._cached_value
            logger.warning("No cached F&G value, defaulting to 50.")
            return 50

    async def fetch_history(self, days: int = 30) -> list[dict]:
        """Return list of {value, timestamp, value_classification} for N days."""
        now = time.time()
        if self._cached_history is not None and (now - self._last_history_ts) < _CACHE_TTL:
            return self._cached_history

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    _FNG_API, params={"limit": days, "format": "json"}
                )
                resp.raise_for_status()
                data = resp.json()
                history = [
                    {
                        "value": int(d["value"]),
                        "timestamp": int(d["timestamp"]),
                        "classification": d.get("value_classification", ""),
                    }
                    for d in data.get("data", [])
                ]
                self._cached_history = history
                self._last_history_ts = now
                return history
        except Exception as e:
            logger.warning("Fear & Greed history fetch failed: {}", e)
            if self._cached_history is not None:
                return self._cached_history
            return []

    @staticmethod
    def get_zone(value: int) -> str:
        """Map F&G value to a human-readable zone label."""
        if value <= 10:
            return "extreme_fear"
        if value <= 25:
            return "fear"
        if value <= 55:
            return "neutral"
        if value <= 75:
            return "greed"
        return "extreme_greed"

    @staticmethod
    def get_dca_multiplier(value: int) -> float:
        """Return DCA multiplier based on Fear & Greed value.

        Lower F&G (more fear) -> higher multiplier (buy more).
        """
        if value <= 10:
            return 3.0
        if value <= 25:
            return 2.0
        if value <= 40:
            return 1.5
        if value <= 55:
            return 1.0
        if value <= 75:
            return 0.5
        if value <= 90:
            return 0.25
        return 0.0
