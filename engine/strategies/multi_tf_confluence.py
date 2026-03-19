"""Multi-timeframe confluence filter.

Not a strategy itself — used by other strategies to weight signal confidence
based on alignment across daily, 4-hour, and 1-hour timeframes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import pandas as pd
from loguru import logger

from engine.indicators.trend_indicators import (
    calc_ema,
    calc_macd,
    calc_adx,
    calc_supertrend,
)
from engine.indicators.momentum_indicators import calc_rsi
from engine.utils.constants import Side


@dataclass
class TFBias:
    """Directional bias for a single timeframe."""

    timeframe: str
    side: Optional[Side] = None  # LONG / SHORT / None (neutral)
    strength: float = 0.0  # 0.0 – 1.0


@dataclass
class ConfluenceResult:
    """Aggregated result across all checked timeframes."""

    aligned_count: int  # how many TFs agree
    dominant_side: Optional[Side] = None
    multiplier: float = 1.0
    details: list[TFBias] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.details is None:
            self.details = []


# ── Confluence engine ────────────────────────────────────────────────────────

class MultiTFConfluence:
    """Check 1d / 4h / 1h alignment and return a confidence multiplier.

    Multiplier rules:
      3 TFs same direction → ×1.5
      2 TFs same direction → ×1.0
      1 TF only            → ×0.3
      0 TFs agree          → void (×0.0)
    """

    TIMEFRAMES = ["1d", "4h", "1h"]

    def __init__(self, exchange: Any) -> None:
        self.exchange = exchange

    async def check(
        self,
        symbol: str,
        target_side: Optional[Side] = None,
    ) -> ConfluenceResult:
        """Fetch data for each TF, derive bias, compute alignment."""
        biases: list[TFBias] = []

        for tf in self.TIMEFRAMES:
            bias = await self._get_bias(symbol, tf)
            biases.append(bias)

        return self._aggregate(biases, target_side)

    # ── Per-timeframe bias ───────────────────────────────────────────────

    async def _get_bias(self, symbol: str, timeframe: str) -> TFBias:
        try:
            df = await self._fetch_ohlcv(symbol, timeframe)
            if df is None or len(df) < 200:
                return TFBias(timeframe=timeframe)

            # Compute indicators
            df = calc_ema(df, 10)
            df = calc_ema(df, 50)
            df = calc_macd(df)
            df = calc_adx(df)
            df = calc_rsi(df)
            df = calc_supertrend(df)

            last = df.iloc[-1]

            bullish_signals = 0
            bearish_signals = 0
            total_checks = 5

            # EMA cross
            if last.get("ema_10", 0) > last.get("ema_50", 0):
                bullish_signals += 1
            else:
                bearish_signals += 1

            # MACD
            if last.get("macd", 0) > last.get("macd_signal", 0):
                bullish_signals += 1
            else:
                bearish_signals += 1

            # ADX direction
            if last.get("adx_pos", 0) > last.get("adx_neg", 0):
                bullish_signals += 1
            else:
                bearish_signals += 1

            # RSI
            rsi = last.get("rsi_14", 50)
            if rsi > 50:
                bullish_signals += 1
            elif rsi < 50:
                bearish_signals += 1

            # SuperTrend
            if last.get("supertrend_direction", 0) == 1:
                bullish_signals += 1
            else:
                bearish_signals += 1

            # Determine bias
            if bullish_signals >= 4:
                side = Side.LONG
                strength = bullish_signals / total_checks
            elif bearish_signals >= 4:
                side = Side.SHORT
                strength = bearish_signals / total_checks
            else:
                side = None
                strength = max(bullish_signals, bearish_signals) / total_checks

            return TFBias(timeframe=timeframe, side=side, strength=strength)

        except Exception:
            logger.exception("MultiTF bias error: {} {}", symbol, timeframe)
            return TFBias(timeframe=timeframe)

    # ── Aggregation ──────────────────────────────────────────────────────

    @staticmethod
    def _aggregate(
        biases: list[TFBias],
        target_side: Optional[Side] = None,
    ) -> ConfluenceResult:
        long_count = sum(1 for b in biases if b.side == Side.LONG)
        short_count = sum(1 for b in biases if b.side == Side.SHORT)

        if long_count > short_count:
            dominant = Side.LONG
            aligned = long_count
        elif short_count > long_count:
            dominant = Side.SHORT
            aligned = short_count
        else:
            dominant = None
            aligned = 0

        # If caller specified a target side, count agreement with that side
        if target_side is not None:
            aligned = sum(1 for b in biases if b.side == target_side)
            dominant = target_side

        multiplier_map = {3: 1.5, 2: 1.0, 1: 0.3, 0: 0.0}
        multiplier = multiplier_map.get(aligned, 0.0)

        return ConfluenceResult(
            aligned_count=aligned,
            dominant_side=dominant,
            multiplier=multiplier,
            details=biases,
        )

    # ── Data fetch ───────────────────────────────────────────────────────

    async def _fetch_ohlcv(
        self, symbol: str, timeframe: str, limit: int = 300
    ) -> Optional[pd.DataFrame]:
        try:
            ohlcv = await self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            if not ohlcv:
                return None
            df = pd.DataFrame(
                ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"]
            )
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            return df
        except Exception:
            logger.exception("Failed to fetch OHLCV: {} {}", symbol, timeframe)
            return None
