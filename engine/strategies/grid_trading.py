"""Dynamic grid trading strategy.

Grid rules:
  - 15-30 levels based on 30-day range and ATR
  - Auto-adjust when price skews 80%+ toward grid edge
  - Pause when ADX > 30 (strong trend)
  - Maker orders only
  - Stop when price breaks -5% below grid range
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
import pandas as pd
from loguru import logger
import ta as ta_lib

from engine.config import TradingConfig
from engine.indicators.trend_indicators import calc_adx
from engine.strategies.base_strategy import BaseStrategy, Signal
from engine.utils.constants import Side

MIN_LEVELS = 15
MAX_LEVELS = 30
SKEW_THRESHOLD = 0.80
ADX_PAUSE_THRESHOLD = 30
BREAK_STOP_PCT = -0.05


@dataclass
class GridState:
    symbol: str
    lower: float = 0.0
    upper: float = 0.0
    levels: list[float] = field(default_factory=list)
    active_buys: set[int] = field(default_factory=set)
    active_sells: set[int] = field(default_factory=set)
    paused: bool = False


class GridTrading(BaseStrategy):
    name = "grid_trading"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._cycle_interval = 30.0
        self._grids: dict[str, GridState] = {}

    async def generate_signal(self, symbol: str) -> Optional[Signal]:
        df = await self._fetch(symbol, "1h", 720)  # 30 days
        if df is None or len(df) < 200:
            return None

        df = self._compute_indicators(df)
        last = df.iloc[-1]
        price = float(last["close"])
        adx = float(last.get("adx", 0))
        atr = float(last.get("atr", 0))

        grid = self._grids.get(symbol)

        # ── Initialise grid ──────────────────────────────────────────
        if grid is None:
            grid = self._create_grid(symbol, df, atr)
            self._grids[symbol] = grid
            logger.info(
                "[Grid] Created grid for {}: {:.2f}-{:.2f}, {} levels",
                symbol, grid.lower, grid.upper, len(grid.levels),
            )

        # ── ADX pause ────────────────────────────────────────────────
        if adx > ADX_PAUSE_THRESHOLD:
            if not grid.paused:
                grid.paused = True
                logger.info("[Grid] Paused {} — ADX={:.1f}", symbol, adx)
            return None
        grid.paused = False

        # ── Break stop ───────────────────────────────────────────────
        if price < grid.lower * (1 + BREAK_STOP_PCT):
            logger.warning("[Grid] STOP {} — price {:.2f} broke -5% below grid", symbol, price)
            self._grids.pop(symbol, None)
            return Signal(
                symbol=symbol,
                side=Side.SELL,
                confidence=1.0,
                strategy_name=self.name,
                reason="Grid break stop -5%",
                entry_price=price,
                metadata={"grid_lower": grid.lower, "break": True},
            )

        # ── Skew auto-adjust ─────────────────────────────────────────
        if grid.upper > grid.lower:
            position_in_grid = (price - grid.lower) / (grid.upper - grid.lower)
            if position_in_grid >= SKEW_THRESHOLD or position_in_grid <= (1 - SKEW_THRESHOLD):
                logger.info("[Grid] Re-centering grid for {} (skew={:.2%})", symbol, position_in_grid)
                grid = self._create_grid(symbol, df, atr)
                self._grids[symbol] = grid

        # ── Find nearest grid level for order ────────────────────────
        signal = self._find_grid_signal(grid, price)
        return signal

    # ── Grid creation ────────────────────────────────────────────────────

    def _create_grid(
        self, symbol: str, df: pd.DataFrame, atr: float
    ) -> GridState:
        high_30d = float(df["high"].tail(720).max())
        low_30d = float(df["low"].tail(720).min())
        range_30d = high_30d - low_30d

        if range_30d == 0 or atr == 0:
            num_levels = MIN_LEVELS
        else:
            # More levels when range is large relative to ATR
            ratio = range_30d / atr
            num_levels = int(np.clip(ratio * 1.5, MIN_LEVELS, MAX_LEVELS))

        # Expand range slightly with ATR padding
        lower = low_30d - atr * 0.5
        upper = high_30d + atr * 0.5

        levels = list(np.linspace(lower, upper, num_levels))

        return GridState(symbol=symbol, lower=lower, upper=upper, levels=levels)

    # ── Grid signal logic ────────────────────────────────────────────────

    def _find_grid_signal(self, grid: GridState, price: float) -> Optional[Signal]:
        if not grid.levels:
            return None

        # Find the nearest level below and above price
        below: Optional[float] = None
        above: Optional[float] = None
        below_idx: Optional[int] = None
        above_idx: Optional[int] = None

        for i, level in enumerate(grid.levels):
            if level <= price:
                if below is None or level > below:
                    below = level
                    below_idx = i
            else:
                if above is None or level < above:
                    above = level
                    above_idx = i

        # Buy at nearest level below (maker limit order)
        if below_idx is not None and below_idx not in grid.active_buys:
            grid.active_buys.add(below_idx)
            return Signal(
                symbol=grid.symbol,
                side=Side.BUY,
                confidence=0.5,
                strategy_name=self.name,
                reason=f"Grid buy level {below_idx} at {below:.2f}",
                entry_price=below,
                take_profit=above,
                metadata={
                    "grid_level": below_idx,
                    "order_type": "limit",  # maker only
                },
            )

        # Sell at nearest level above
        if above_idx is not None and above_idx not in grid.active_sells:
            grid.active_sells.add(above_idx)
            return Signal(
                symbol=grid.symbol,
                side=Side.SELL,
                confidence=0.5,
                strategy_name=self.name,
                reason=f"Grid sell level {above_idx} at {above:.2f}",
                entry_price=above,
                metadata={
                    "grid_level": above_idx,
                    "order_type": "limit",
                },
            )

        return None

    # ── Indicators ───────────────────────────────────────────────────────

    @staticmethod
    def _compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
        df = calc_adx(df)
        atr_ind = ta_lib.volatility.AverageTrueRange(
            high=df["high"], low=df["low"], close=df["close"], window=14
        )
        df["atr"] = atr_ind.average_true_range()
        return df

    # ── Data fetch ───────────────────────────────────────────────────────

    async def _fetch(
        self, symbol: str, timeframe: str, limit: int = 720
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
            logger.exception("[Grid] Fetch error: {} {}", symbol, timeframe)
            return None
