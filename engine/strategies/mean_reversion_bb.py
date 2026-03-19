"""Mean-reversion strategy using Bollinger Bands.

Entry conditions (all must be true):
  - Price < BB lower band
  - RSI(14) < 30
  - ADX < 25 (no strong trend)
  - Stochastic %K < 20
  - Price > SMA(200) (long-term uptrend intact)

Exit:
  - TP1: BB middle — close 50% of position
  - TP2: BB upper — close remaining
  - RSI > 65 → exit all
  - SL: -3% from entry or BB lower - 2×ATR (whichever is tighter)
"""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd
from loguru import logger
import ta as ta_lib

from engine.config import TradingConfig
from engine.indicators.trend_indicators import calc_sma, calc_adx
from engine.indicators.momentum_indicators import calc_rsi, calc_stochastic
from engine.strategies.base_strategy import BaseStrategy, Signal
from engine.utils.constants import Side


class MeanReversionBB(BaseStrategy):
    name = "mean_reversion_bb"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._cycle_interval = 120.0

    async def generate_signal(self, symbol: str) -> Optional[Signal]:
        df = await self._fetch(symbol, "1h", 300)
        if df is None or len(df) < 200:
            return None

        df = self._compute_indicators(df)
        last = df.iloc[-1]

        price = float(last["close"])
        bb_lower = float(last.get("bb_lower", 0))
        bb_middle = float(last.get("bb_middle", 0))
        bb_upper = float(last.get("bb_upper", 0))
        rsi = float(last.get("rsi_14", 50))
        adx = float(last.get("adx", 0))
        stoch_k = float(last.get("stoch_k", 50))
        sma200 = float(last.get("sma_200", 0))
        atr = float(last.get("atr", 0))

        # ── Entry conditions ─────────────────────────────────────────
        if price >= bb_lower:
            return None
        if rsi >= 30:
            return None
        if adx >= 25:
            return None
        if stoch_k >= 20:
            return None
        if price <= sma200:
            return None

        # ── Stop loss: tighter of -3% or BB lower - 2×ATR ───────────
        sl_pct = price * 0.97
        sl_atr = bb_lower - 2 * atr if atr > 0 else sl_pct
        stop_loss = max(sl_pct, sl_atr)  # tighter = higher value

        # ── Take profit levels ───────────────────────────────────────
        tp1 = bb_middle  # 50% exit
        tp2 = bb_upper   # remaining

        confidence = 0.7
        # Stronger signal if very oversold
        if rsi < 20 and stoch_k < 10:
            confidence = 0.85

        return Signal(
            symbol=symbol,
            side=Side.LONG,
            confidence=confidence,
            strategy_name=self.name,
            reason=(
                f"BB reversion: RSI={rsi:.1f} Stoch={stoch_k:.1f} "
                f"ADX={adx:.1f} price<BB_lower"
            ),
            entry_price=price,
            stop_loss=stop_loss,
            take_profit=tp1,  # primary TP
            metadata={
                "tp1": tp1,
                "tp1_pct": 0.50,
                "tp2": tp2,
                "tp2_pct": 0.50,
                "bb_lower": bb_lower,
                "atr": atr,
                "rsi_exit_threshold": 65,
            },
        )

    # ── Exit check (called by position manager) ─────────────────────────

    def check_exit(self, last: pd.Series) -> tuple[bool, str]:
        rsi = float(last.get("rsi_14", 50))
        if rsi > 65:
            return True, f"RSI exit ({rsi:.1f} > 65)"
        return False, ""

    # ── Indicators ───────────────────────────────────────────────────────

    @staticmethod
    def _compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
        df = calc_sma(df, 200)
        df = calc_adx(df)
        df = calc_rsi(df)
        df = calc_stochastic(df)

        bb = ta_lib.volatility.BollingerBands(close=df["close"], window=20, window_dev=2)
        df["bb_lower"] = bb.bollinger_lband()
        df["bb_middle"] = bb.bollinger_mavg()
        df["bb_upper"] = bb.bollinger_hband()

        atr_ind = ta_lib.volatility.AverageTrueRange(
            high=df["high"], low=df["low"], close=df["close"], window=14
        )
        df["atr"] = atr_ind.average_true_range()

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
            logger.exception("[MeanRevBB] Fetch error: {} {}", symbol, timeframe)
            return None
