"""Momentum breakout strategy.

Entry conditions:
  - Price breaks above Donchian(20) upper channel
  - Volume > 2× average (20-period SMA)
  - ROC > 0
  - ADX > 20
  - RSI between 40 and 70

Fakeout filters:
  - 2-candle hold above breakout level
  - Body ratio >= 60% (body / full range)
  - Bollinger squeeze bonus (bandwidth < 20th percentile)

Exit: Trailing stop at ATR(14) × 2.5
"""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd
from loguru import logger
import ta as ta_lib

from engine.config import TradingConfig
from engine.indicators.trend_indicators import calc_adx
from engine.indicators.momentum_indicators import calc_rsi, calc_roc
from engine.strategies.base_strategy import BaseStrategy, Signal
from engine.utils.constants import Side


class MomentumBreakout(BaseStrategy):
    name = "momentum_breakout"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._cycle_interval = 120.0

    async def generate_signal(self, symbol: str) -> Optional[Signal]:
        df = await self._fetch(symbol, "1h", 300)
        if df is None or len(df) < 50:
            return None

        df = self._compute_indicators(df)
        last = df.iloc[-1]
        prev = df.iloc[-2]
        prev2 = df.iloc[-3]

        price = float(last["close"])
        donchian_upper = float(last.get("donchian_upper", 0))

        # ── Breakout check ───────────────────────────────────────────
        if price <= donchian_upper:
            return None

        # Volume > 2× average
        vol = float(last.get("volume", 0))
        vol_sma = float(last.get("vol_sma_20", 0))
        if vol_sma > 0 and vol <= 2 * vol_sma:
            return None

        # ROC > 0
        roc = float(last.get("roc_12", 0))
        if roc <= 0:
            return None

        # ADX > 20
        adx = float(last.get("adx", 0))
        if adx <= 20:
            return None

        # RSI 40-70
        rsi = float(last.get("rsi_14", 50))
        if rsi < 40 or rsi > 70:
            return None

        # ── Fakeout filters ──────────────────────────────────────────

        # 2-candle hold: previous candle also above the prior Donchian upper
        prev_donchian = float(prev.get("donchian_upper", 0))
        if float(prev["close"]) <= prev_donchian:
            return None  # need 2 candles above

        # Body ratio >= 60%
        body = abs(float(last["close"]) - float(last["open"]))
        full_range = float(last["high"]) - float(last["low"])
        if full_range > 0 and (body / full_range) < 0.60:
            return None

        # ── Confidence & Bollinger squeeze bonus ─────────────────────
        confidence = 0.65
        bb_width = float(last.get("bb_bandwidth", 0))
        bb_width_pct20 = float(last.get("bb_bandwidth_pct20", float("inf")))
        if bb_width > 0 and bb_width < bb_width_pct20:
            confidence = min(1.0, confidence + 0.15)

        # ATR trailing stop
        atr = float(last.get("atr", 0))
        stop_loss = price - 2.5 * atr if atr > 0 else None

        reasons = [
            f"Donchian breakout",
            f"Vol={vol / vol_sma:.1f}x" if vol_sma > 0 else "",
            f"ROC={roc:.2f}",
            f"ADX={adx:.1f}",
            f"RSI={rsi:.1f}",
        ]

        return Signal(
            symbol=symbol,
            side=Side.LONG,
            confidence=confidence,
            strategy_name=self.name,
            reason=" | ".join(r for r in reasons if r),
            entry_price=price,
            stop_loss=stop_loss,
            metadata={
                "atr": atr,
                "donchian_upper": donchian_upper,
                "body_ratio": body / full_range if full_range > 0 else 0,
                "bb_squeeze": bb_width < bb_width_pct20 if bb_width > 0 else False,
            },
        )

    # ── Indicators ───────────────────────────────────────────────────────

    @staticmethod
    def _compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
        df = calc_adx(df)
        df = calc_rsi(df)
        df = calc_roc(df, 12)

        # Donchian channel (20)
        df["donchian_upper"] = df["high"].rolling(window=20).max()
        df["donchian_lower"] = df["low"].rolling(window=20).min()

        # Volume SMA
        df["vol_sma_20"] = df["volume"].rolling(window=20).mean()

        # ATR
        atr_ind = ta_lib.volatility.AverageTrueRange(
            high=df["high"], low=df["low"], close=df["close"], window=14
        )
        df["atr"] = atr_ind.average_true_range()

        # Bollinger bandwidth for squeeze detection
        bb = ta_lib.volatility.BollingerBands(close=df["close"], window=20, window_dev=2)
        df["bb_upper"] = bb.bollinger_hband()
        df["bb_lower"] = bb.bollinger_lband()
        df["bb_middle"] = bb.bollinger_mavg()
        bb_mid = df["bb_middle"].replace(0, float("nan"))
        df["bb_bandwidth"] = (df["bb_upper"] - df["bb_lower"]) / bb_mid
        df["bb_bandwidth_pct20"] = df["bb_bandwidth"].rolling(window=120).quantile(0.20)

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
            logger.exception("[MomentumBreakout] Fetch error: {} {}", symbol, timeframe)
            return None
