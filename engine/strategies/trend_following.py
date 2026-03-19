"""Trend-following strategy.

Entry conditions (all must be true):
  - Price > SMA(200)
  - EMA(10) > EMA(50)
  - ADX > 25
  - MACD line > 0
  - Volume > SMA(20) of volume
  - 4h EMA(10) > EMA(50)

Confirmation: SuperTrend bullish + price above Ichimoku cloud.
Pullback entry: price touches EMA(21) in an uptrend.

Exit:
  - Trailing stop at ATR(14) × 2
  - EMA(10) / EMA(50) death cross
  - ADX drops below 20
"""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd
from loguru import logger

from engine.config import TradingConfig
from engine.indicators.trend_indicators import (
    calc_sma,
    calc_ema,
    calc_macd,
    calc_adx,
    calc_supertrend,
    calc_ichimoku,
)
from engine.indicators.momentum_indicators import calc_rsi
from engine.strategies.base_strategy import BaseStrategy, Signal
from engine.strategies.multi_tf_confluence import MultiTFConfluence
from engine.utils.constants import Side

import ta


class TrendFollowing(BaseStrategy):
    name = "trend_following"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._cycle_interval = 300.0  # 5 min
        self._mtf = MultiTFConfluence(self.exchange)

    # ── Signal generation ────────────────────────────────────────────────

    async def generate_signal(self, symbol: str) -> Optional[Signal]:
        df_1h = await self._fetch(symbol, "1h", 300)
        df_4h = await self._fetch(symbol, "4h", 200)
        if df_1h is None or df_4h is None:
            return None

        df = self._compute_indicators(df_1h)
        df_4h = self._compute_4h_indicators(df_4h)

        last = df.iloc[-1]
        last_4h = df_4h.iloc[-1]

        # ── Entry check ──────────────────────────────────────────────
        entry, reason = self._check_entry(last, last_4h, df)
        if not entry:
            # Check pullback entry
            entry, reason = self._check_pullback(last, last_4h, df)
            if not entry:
                return None

        # Confirmation: SuperTrend + Ichimoku
        if not self._confirm(last):
            return None

        # Multi-TF confluence
        confluence = await self._mtf.check(symbol, Side.LONG)
        if confluence.multiplier == 0.0:
            return None

        confidence = min(1.0, 0.7 * confluence.multiplier)

        atr = last.get("atr", 0)
        entry_price = float(last["close"])
        stop_loss = entry_price - 2.0 * atr if atr > 0 else None
        take_profit = entry_price + 4.0 * atr if atr > 0 else None

        return Signal(
            symbol=symbol,
            side=Side.LONG,
            confidence=confidence,
            strategy_name=self.name,
            reason=reason,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            metadata={"atr": atr, "adx": float(last.get("adx", 0))},
        )

    # ── Entry conditions ─────────────────────────────────────────────────

    def _check_entry(
        self, last: pd.Series, last_4h: pd.Series, df: pd.DataFrame
    ) -> tuple[bool, str]:
        reasons: list[str] = []

        price = last["close"]
        sma200 = last.get("sma_200", 0)
        ema10 = last.get("ema_10", 0)
        ema50 = last.get("ema_50", 0)
        adx = last.get("adx", 0)
        macd = last.get("macd", 0)
        vol = last.get("volume", 0)
        vol_sma = last.get("vol_sma_20", 0)
        ema10_4h = last_4h.get("ema_10", 0)
        ema50_4h = last_4h.get("ema_50", 0)

        if price <= sma200:
            return False, ""
        reasons.append("price>SMA200")

        if ema10 <= ema50:
            return False, ""
        reasons.append("EMA10>EMA50")

        if adx <= 25:
            return False, ""
        reasons.append(f"ADX={adx:.1f}")

        if macd <= 0:
            return False, ""
        reasons.append("MACD>0")

        if vol <= vol_sma:
            return False, ""
        reasons.append("Vol>SMA20vol")

        if ema10_4h <= ema50_4h:
            return False, ""
        reasons.append("4h_EMA_golden")

        return True, " | ".join(reasons)

    def _check_pullback(
        self, last: pd.Series, last_4h: pd.Series, df: pd.DataFrame
    ) -> tuple[bool, str]:
        """Pullback entry: price near EMA(21) in confirmed uptrend."""
        price = last["close"]
        ema21 = last.get("ema_21", 0)
        sma200 = last.get("sma_200", 0)
        adx = last.get("adx", 0)

        if price <= sma200 or adx <= 25:
            return False, ""

        # Price within 0.5% of EMA21
        if ema21 == 0:
            return False, ""
        distance_pct = abs(price - ema21) / ema21
        if distance_pct > 0.005:
            return False, ""

        # Uptrend confirmation: EMA10 > EMA50
        if last.get("ema_10", 0) <= last.get("ema_50", 0):
            return False, ""

        return True, f"Pullback to EMA21 (dist={distance_pct:.3%})"

    # ── Confirmation ─────────────────────────────────────────────────────

    @staticmethod
    def _confirm(last: pd.Series) -> bool:
        # SuperTrend bullish
        if last.get("supertrend_direction", 0) != 1:
            return False
        # Price above Ichimoku cloud
        senkou_a = last.get("ichimoku_senkou_a", 0)
        senkou_b = last.get("ichimoku_senkou_b", 0)
        cloud_top = max(senkou_a, senkou_b)
        if last["close"] <= cloud_top:
            return False
        return True

    # ── Exit conditions (checked externally by position manager) ─────────

    def check_exit(self, last: pd.Series) -> tuple[bool, str]:
        """Return (should_exit, reason)."""
        # EMA death cross
        if last.get("ema_10", 0) < last.get("ema_50", 0):
            return True, "EMA death cross"
        # ADX weakening
        if last.get("adx", 0) < 20:
            return True, "ADX < 20"
        return False, ""

    # ── Indicator computation ────────────────────────────────────────────

    @staticmethod
    def _compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
        df = calc_sma(df, 200)
        df = calc_ema(df, 10)
        df = calc_ema(df, 21)
        df = calc_ema(df, 50)
        df = calc_macd(df)
        df = calc_adx(df)
        df = calc_supertrend(df)
        df = calc_ichimoku(df)

        # Volume SMA
        df["vol_sma_20"] = df["volume"].rolling(window=20).mean()

        # ATR for trailing stop
        atr_ind = ta.volatility.AverageTrueRange(
            high=df["high"], low=df["low"], close=df["close"], window=14
        )
        df["atr"] = atr_ind.average_true_range()

        return df

    @staticmethod
    def _compute_4h_indicators(df: pd.DataFrame) -> pd.DataFrame:
        df = calc_ema(df, 10)
        df = calc_ema(df, 50)
        return df

    # ── Data fetch ───────────────────────────────────────────────────────

    async def _fetch(
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
            logger.exception("[TrendFollowing] Fetch error: {} {}", symbol, timeframe)
            return None
