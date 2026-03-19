"""Smart DCA strategy — Fear & Greed weighted dollar-cost averaging.

Rules:
  - Only BTC/ETH
  - RSI < 40 to start a new DCA series
  - Base order: 5% of capital × F&G multiplier
  - 6 safety orders at -2% / -3.5% / -5.5% / -8% / -11% / -15%
    with 1.5× volume scaling per level
  - Bollinger lower band touch → bonus boost to order size
  - Exit when average price + 1.5% reached
  - Hard stop: -20% max loss cut from average entry
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd
from loguru import logger
import ta as ta_lib

from engine.config import TradingConfig
from engine.indicators.momentum_indicators import calc_rsi
from engine.strategies.base_strategy import BaseStrategy, Signal
from engine.utils.constants import Side


ALLOWED_SYMBOLS = {"BTC/USDT", "ETH/USDT", "BTC/USDT:USDT", "ETH/USDT:USDT"}

SAFETY_ORDER_DROPS = [-0.02, -0.035, -0.055, -0.08, -0.11, -0.15]
SAFETY_VOLUME_SCALE = 1.5
BASE_ORDER_PCT = 0.05
EXIT_PROFIT_PCT = 0.015
MAX_LOSS_PCT = -0.20
BOLLINGER_BOOST = 1.3


@dataclass
class DCAState:
    """Tracks an active DCA series for a symbol."""

    symbol: str
    entries: list[tuple[float, float]] = field(default_factory=list)  # (price, amount)
    safety_level: int = 0  # next safety order index
    active: bool = False

    @property
    def avg_price(self) -> float:
        if not self.entries:
            return 0.0
        total_cost = sum(p * a for p, a in self.entries)
        total_amount = sum(a for _, a in self.entries)
        return total_cost / total_amount if total_amount > 0 else 0.0

    @property
    def total_amount(self) -> float:
        return sum(a for _, a in self.entries)


class SmartDCA(BaseStrategy):
    name = "smart_dca"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._cycle_interval = 60.0
        self._dca_states: dict[str, DCAState] = {}
        self._fear_greed_fetcher: Any = kwargs.get("fear_greed_fetcher")

    async def generate_signal(self, symbol: str) -> Optional[Signal]:
        if not self._is_allowed(symbol):
            return None

        df = await self._fetch(symbol, "1h", 200)
        if df is None:
            return None

        df = self._compute_indicators(df)
        last = df.iloc[-1]
        price = float(last["close"])

        state = self._dca_states.get(symbol)

        # ── Active DCA series → check safety orders or exit ──────────
        if state and state.active:
            return await self._manage_active(state, price, last)

        # ── No active DCA → check if we should start one ────────────
        rsi = last.get("rsi_14", 50)
        if rsi >= 40:
            return None

        fg_mult = await self._fg_multiplier()
        base_size = BASE_ORDER_PCT * fg_mult

        # Bollinger lower band boost
        bb_lower = last.get("bb_lower", 0)
        if bb_lower > 0 and price <= bb_lower:
            base_size *= BOLLINGER_BOOST

        state = DCAState(symbol=symbol, active=True)
        state.entries.append((price, base_size))
        self._dca_states[symbol] = state

        logger.info(
            "[SmartDCA] Starting DCA for {} at {:.2f}, size={:.4f}, RSI={:.1f}",
            symbol, price, base_size, rsi,
        )

        return Signal(
            symbol=symbol,
            side=Side.BUY,
            confidence=0.7,
            strategy_name=self.name,
            reason=f"DCA start RSI={rsi:.1f} F&G_mult={fg_mult:.2f}",
            entry_price=price,
            size_multiplier=base_size,
            metadata={"dca_level": 0, "rsi": rsi, "fg_mult": fg_mult},
        )

    # ── Manage active DCA ────────────────────────────────────────────────

    async def _manage_active(
        self, state: DCAState, price: float, last: pd.Series
    ) -> Optional[Signal]:
        avg = state.avg_price
        if avg == 0:
            return None

        pnl_pct = (price - avg) / avg

        # Exit: profit target
        if pnl_pct >= EXIT_PROFIT_PCT:
            state.active = False
            logger.info(
                "[SmartDCA] Exit {} at {:.2f}, avg={:.2f}, pnl={:.2%}",
                state.symbol, price, avg, pnl_pct,
            )
            return Signal(
                symbol=state.symbol,
                side=Side.SELL,
                confidence=0.9,
                strategy_name=self.name,
                reason=f"DCA TP avg+{EXIT_PROFIT_PCT:.1%} reached",
                entry_price=price,
                size_multiplier=state.total_amount,
                metadata={"pnl_pct": pnl_pct},
            )

        # Hard stop
        if pnl_pct <= MAX_LOSS_PCT:
            state.active = False
            logger.warning(
                "[SmartDCA] STOP LOSS {} at {:.2f}, loss={:.2%}",
                state.symbol, price, pnl_pct,
            )
            return Signal(
                symbol=state.symbol,
                side=Side.SELL,
                confidence=1.0,
                strategy_name=self.name,
                reason=f"DCA max loss {MAX_LOSS_PCT:.0%} hit",
                entry_price=price,
                size_multiplier=state.total_amount,
                metadata={"pnl_pct": pnl_pct, "stop_loss": True},
            )

        # Safety orders
        if state.safety_level < len(SAFETY_ORDER_DROPS):
            trigger_pct = SAFETY_ORDER_DROPS[state.safety_level]
            first_entry_price = state.entries[0][0]
            trigger_price = first_entry_price * (1 + trigger_pct)

            if price <= trigger_price:
                level = state.safety_level
                prev_size = state.entries[-1][1]
                order_size = prev_size * SAFETY_VOLUME_SCALE

                # Bollinger boost
                bb_lower = last.get("bb_lower", 0)
                if bb_lower > 0 and price <= bb_lower:
                    order_size *= BOLLINGER_BOOST

                state.entries.append((price, order_size))
                state.safety_level += 1

                logger.info(
                    "[SmartDCA] Safety order #{} for {} at {:.2f}, size={:.4f}",
                    level + 1, state.symbol, price, order_size,
                )

                return Signal(
                    symbol=state.symbol,
                    side=Side.BUY,
                    confidence=0.6,
                    strategy_name=self.name,
                    reason=f"Safety order #{level + 1} at {trigger_pct:.1%}",
                    entry_price=price,
                    size_multiplier=order_size,
                    metadata={"dca_level": level + 1, "avg_price": state.avg_price},
                )

        return None

    # ── Fear & Greed multiplier ──────────────────────────────────────────

    async def _fg_multiplier(self) -> float:
        """F&G < 20 → 2.0×, 20-40 → 1.5×, 40-60 → 1.0×, >60 → 0.5×."""
        if self._fear_greed_fetcher is None:
            return 1.0
        try:
            fg = await self._fear_greed_fetcher.get()
            value = fg if isinstance(fg, (int, float)) else fg.get("value", 50)
            if value < 20:
                return 2.0
            if value < 40:
                return 1.5
            if value < 60:
                return 1.0
            return 0.5
        except Exception:
            return 1.0

    # ── Helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _is_allowed(symbol: str) -> bool:
        base = symbol.split("/")[0].upper() if "/" in symbol else symbol.upper()
        return base in ("BTC", "ETH") or symbol in ALLOWED_SYMBOLS

    @staticmethod
    def _compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
        df = calc_rsi(df)
        bb = ta_lib.volatility.BollingerBands(close=df["close"], window=20, window_dev=2)
        df["bb_lower"] = bb.bollinger_lband()
        df["bb_middle"] = bb.bollinger_mavg()
        df["bb_upper"] = bb.bollinger_hband()
        return df

    async def _fetch(
        self, symbol: str, timeframe: str, limit: int = 200
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
            logger.exception("[SmartDCA] Fetch error: {} {}", symbol, timeframe)
            return None
