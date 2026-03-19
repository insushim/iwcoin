"""Strategy allocation based on detected market regime."""

from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from loguru import logger

from engine.config import TradingConfig
from engine.regime.regime_detector import Regime, RegimeDetector


# Allocation presets per regime
_ALLOCATIONS: dict[Regime, dict] = {
    Regime.BULL: {
        "strategies": {
            "trend_following": 0.40,
            "momentum": 0.30,
            "rebalancer": 0.20,
            "funding_arb": 0.10,
        },
        "capital_usage": 0.80,
    },
    Regime.SIDEWAYS: {
        "strategies": {
            "grid": 0.35,
            "mean_reversion": 0.25,
            "funding_arb": 0.20,
            "dca": 0.10,
        },
        "capital_usage": 0.60,
    },
    Regime.BEAR: {
        "strategies": {
            "dca": 0.40,
            "funding_arb": 0.20,
            "mean_reversion": 0.10,
        },
        "capital_usage": 0.40,
    },
    Regime.UNCERTAIN: {
        "strategies": {
            "dca": 1.0,
        },
        "capital_usage": 0.20,
    },
}

_REGIME_SWITCH_THRESHOLD = 3  # consecutive same regime before switching


class RegimeAllocator:
    """Allocates strategy weights based on current market regime with hysteresis."""

    def __init__(self, regime_detector: RegimeDetector, config: TradingConfig) -> None:
        self._detector = regime_detector
        self._config = config
        self._current_regime: Regime = Regime.UNCERTAIN
        self._regime_history: deque[Regime] = deque(maxlen=_REGIME_SWITCH_THRESHOLD)
        self._last_allocation: Optional[dict] = None

    @property
    def current_regime(self) -> Regime:
        return self._current_regime

    async def allocate(self, symbol: str = "BTC/USDT") -> dict:
        """Detect regime and return strategy allocation dict.

        Returns:
            {
                "regime": str,
                "previous_regime": str,
                "capital_usage": float,
                "strategies": {name: weight, ...},
                "regime_changed": bool,
                "consecutive_count": int,
                "timestamp": str,
            }
        """
        detection = await self._detector.detect_regime(symbol)
        detected = Regime(detection["regime"])
        previous = self._current_regime

        self._regime_history.append(detected)
        regime_changed = False
        consecutive = sum(1 for r in self._regime_history if r == detected)

        # Only switch if N consecutive same detections
        if consecutive >= _REGIME_SWITCH_THRESHOLD and detected != self._current_regime:
            logger.info(
                "Regime switch: {} -> {} (after {} consecutive detections)",
                self._current_regime.value, detected.value, consecutive,
            )
            self._current_regime = detected
            regime_changed = True
            await self._handle_regime_change(previous, detected, detection)

        preset = _ALLOCATIONS.get(self._current_regime, _ALLOCATIONS[Regime.UNCERTAIN])

        self._last_allocation = {
            "regime": self._current_regime.value,
            "previous_regime": previous.value,
            "capital_usage": preset["capital_usage"],
            "strategies": dict(preset["strategies"]),
            "regime_changed": regime_changed,
            "consecutive_count": consecutive,
            "fear_greed": detection.get("fear_greed", 50),
            "confidence": detection.get("confidence", 0.0),
            "risk_level": detection.get("risk_level", "medium"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        return self._last_allocation

    def get_last_allocation(self) -> Optional[dict]:
        """Return the most recent allocation without re-detecting."""
        return self._last_allocation

    async def _handle_regime_change(
        self, old: Regime, new: Regime, detection: dict
    ) -> None:
        """Execute side-effects on regime change (e.g. Telegram notification)."""
        old_preset = _ALLOCATIONS.get(old, _ALLOCATIONS[Regime.UNCERTAIN])
        new_preset = _ALLOCATIONS.get(new, _ALLOCATIONS[Regime.UNCERTAIN])

        msg = (
            f"🔄 *Regime Change*\n"
            f"  {old.value} → *{new.value}*\n"
            f"  Confidence: {detection.get('confidence', 0):.1%}\n"
            f"  Fear & Greed: {detection.get('fear_greed', '?')}\n"
            f"  Capital: {old_preset['capital_usage']:.0%} → {new_preset['capital_usage']:.0%}\n"
            f"  Risk: {detection.get('risk_level', '?')}\n"
            f"  Strategies: {', '.join(new_preset['strategies'].keys())}"
        )

        await self._send_telegram(msg)

    async def _send_telegram(self, text: str) -> None:
        """Send Telegram notification if configured."""
        token = self._config.telegram_bot_token
        chat_id = self._config.telegram_chat_id
        if not token or not chat_id:
            logger.debug("Telegram not configured, skipping notification.")
            return

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    url,
                    json={
                        "chat_id": chat_id,
                        "text": text,
                        "parse_mode": "Markdown",
                    },
                )
                if resp.status_code != 200:
                    logger.warning("Telegram send failed: {} {}", resp.status_code, resp.text)
        except Exception as e:
            logger.warning("Telegram notification error: {}", e)
