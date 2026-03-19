"""Stop-loss manager – fixed / ATR / trailing, places stop-market orders."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Protocol

from loguru import logger


class StopType(str, Enum):
    FIXED = "fixed"
    ATR = "atr"
    TRAILING = "trailing"


@dataclass
class StopLossConfig:
    # Fixed stop percentages by regime
    fixed_pct: dict[str, float] = field(default_factory=lambda: {
        "BULL": 0.04,
        "SIDEWAYS": 0.03,
        "BEAR": 0.02,
    })
    # ATR-based
    atr_multiplier: float = 2.0
    # Trailing
    trailing_atr_multiplier: float = 2.0
    trailing_activate_pct: float = 0.01   # activate at +1%
    trailing_breakeven_pct: float = 0.03  # move SL to entry at +3%


class ExchangeGateway(Protocol):
    """Minimal exchange interface for placing stop orders."""

    async def create_stop_market_order(
        self, symbol: str, side: str, amount: float, stop_price: float, params: dict
    ) -> dict: ...

    async def cancel_order(self, order_id: str, symbol: str) -> dict: ...


@dataclass
class StopState:
    """Tracks the current stop-loss state for a single position."""
    symbol: str
    direction: str  # "long" or "short"
    entry_price: float
    amount: float
    atr: float
    regime: str

    # Computed stops
    fixed_stop: float = 0.0
    atr_stop: float = 0.0
    trailing_stop: float = 0.0
    active_stop: float = 0.0
    active_type: StopType = StopType.FIXED

    # Trailing state
    highest_price: float = 0.0
    trailing_activated: bool = False
    breakeven_activated: bool = False

    # Exchange order tracking
    stop_order_id: Optional[str] = None


class StopLossManager:
    """Compute and manage stop-loss levels for open positions."""

    def __init__(
        self,
        config: Optional[StopLossConfig] = None,
        exchange: Optional[ExchangeGateway] = None,
    ) -> None:
        self.config = config or StopLossConfig()
        self.exchange = exchange
        self._positions: dict[str, StopState] = {}  # keyed by symbol
        logger.info("StopLossManager initialised | ATR mult={}", self.config.atr_multiplier)

    # ── public API ──────────────────────────────────────────

    async def register_position(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        amount: float,
        atr: float,
        regime: str = "SIDEWAYS",
    ) -> StopState:
        """Register a new position and compute initial stops."""
        state = StopState(
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            amount=amount,
            atr=atr,
            regime=regime.upper(),
            highest_price=entry_price,
        )
        self._compute_stops(state)
        self._positions[symbol] = state

        # Place stop order on exchange
        await self._place_stop_order(state)

        logger.info(
            "Stop registered | {} {} @ {:.4f} | fixed={:.4f} atr={:.4f} active={:.4f} ({})",
            symbol, direction, entry_price,
            state.fixed_stop, state.atr_stop, state.active_stop, state.active_type.value,
        )
        return state

    async def update_price(self, symbol: str, current_price: float) -> Optional[StopState]:
        """Update trailing stop based on latest price. Returns updated state or None."""
        state = self._positions.get(symbol)
        if not state:
            return None

        is_long = state.direction == "long"
        old_stop = state.active_stop

        if is_long:
            if current_price > state.highest_price:
                state.highest_price = current_price

            pnl_pct = (current_price - state.entry_price) / state.entry_price

            # Activate trailing
            if pnl_pct >= self.config.trailing_activate_pct and not state.trailing_activated:
                state.trailing_activated = True
                logger.info("{} trailing stop activated at +{:.2%}", symbol, pnl_pct)

            # Move to breakeven
            if pnl_pct >= self.config.trailing_breakeven_pct and not state.breakeven_activated:
                state.breakeven_activated = True
                logger.info("{} stop moved to breakeven", symbol)

            # Compute trailing stop
            if state.trailing_activated:
                state.trailing_stop = state.highest_price - state.atr * self.config.trailing_atr_multiplier
                if state.breakeven_activated:
                    state.trailing_stop = max(state.trailing_stop, state.entry_price)
        else:
            # Short position – mirror logic
            if current_price < state.highest_price or state.highest_price == state.entry_price:
                state.highest_price = min(state.highest_price, current_price) if state.highest_price != state.entry_price else current_price

            pnl_pct = (state.entry_price - current_price) / state.entry_price

            if pnl_pct >= self.config.trailing_activate_pct and not state.trailing_activated:
                state.trailing_activated = True

            if pnl_pct >= self.config.trailing_breakeven_pct and not state.breakeven_activated:
                state.breakeven_activated = True

            if state.trailing_activated:
                lowest = state.highest_price  # re-used as "best price" for shorts
                state.trailing_stop = lowest + state.atr * self.config.trailing_atr_multiplier
                if state.breakeven_activated:
                    state.trailing_stop = min(state.trailing_stop, state.entry_price)

        # Pick tightest stop
        self._select_tightest(state)

        # Update exchange order if stop changed
        if state.active_stop != old_stop:
            await self._place_stop_order(state)
            logger.debug("{} stop updated {:.4f} -> {:.4f} ({})", symbol, old_stop, state.active_stop, state.active_type.value)

        return state

    async def remove_position(self, symbol: str) -> None:
        """Cancel stop order and remove tracking."""
        state = self._positions.pop(symbol, None)
        if state and state.stop_order_id and self.exchange:
            try:
                await self.exchange.cancel_order(state.stop_order_id, symbol)
            except Exception as e:
                logger.warning("Failed to cancel stop order for {}: {}", symbol, e)

    def get_stop(self, symbol: str) -> Optional[float]:
        state = self._positions.get(symbol)
        return state.active_stop if state else None

    def get_state(self, symbol: str) -> Optional[StopState]:
        return self._positions.get(symbol)

    # ── internals ───────────────────────────────────────────

    def _compute_stops(self, state: StopState) -> None:
        regime = state.regime if state.regime in self.config.fixed_pct else "SIDEWAYS"
        fixed_pct = self.config.fixed_pct[regime]
        is_long = state.direction == "long"

        if is_long:
            state.fixed_stop = state.entry_price * (1 - fixed_pct)
            state.atr_stop = state.entry_price - state.atr * self.config.atr_multiplier
            state.trailing_stop = 0.0  # not active yet
        else:
            state.fixed_stop = state.entry_price * (1 + fixed_pct)
            state.atr_stop = state.entry_price + state.atr * self.config.atr_multiplier
            state.trailing_stop = float("inf")

        self._select_tightest(state)

    def _select_tightest(self, state: StopState) -> None:
        """Select the tightest (closest to current price) stop."""
        is_long = state.direction == "long"

        candidates: list[tuple[StopType, float]] = [
            (StopType.FIXED, state.fixed_stop),
            (StopType.ATR, state.atr_stop),
        ]
        if state.trailing_activated:
            candidates.append((StopType.TRAILING, state.trailing_stop))

        if is_long:
            # Tightest = highest stop price
            best = max(candidates, key=lambda x: x[1])
        else:
            # Tightest = lowest stop price
            valid = [(t, p) for t, p in candidates if p > 0 and p != float("inf")]
            best = min(valid, key=lambda x: x[1]) if valid else candidates[0]

        state.active_type = best[0]
        state.active_stop = best[1]

    async def _place_stop_order(self, state: StopState) -> None:
        if not self.exchange:
            return
        try:
            # Cancel existing stop order
            if state.stop_order_id:
                await self.exchange.cancel_order(state.stop_order_id, state.symbol)

            side = "sell" if state.direction == "long" else "buy"
            result = await self.exchange.create_stop_market_order(
                symbol=state.symbol,
                side=side,
                amount=state.amount,
                stop_price=round(state.active_stop, 8),
                params={"stopPrice": round(state.active_stop, 8), "type": "stop_market"},
            )
            state.stop_order_id = result.get("id")
            logger.debug("Stop order placed for {} @ {:.4f} id={}", state.symbol, state.active_stop, state.stop_order_id)
        except Exception as e:
            logger.error("Failed to place stop order for {}: {}", state.symbol, e)
