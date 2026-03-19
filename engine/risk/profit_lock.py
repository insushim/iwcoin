"""Profit lock – 3-stage take-profit with partial exits and trailing."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional, Protocol

from loguru import logger


class TPStage(IntEnum):
    NONE = 0
    TP1 = 1
    TP2 = 2
    TP3 = 3


@dataclass
class ProfitLockConfig:
    tp1_r_mult: float = 1.0        # entry + R×1
    tp1_sell_pct: float = 0.30     # sell 30%
    tp2_r_mult: float = 2.0        # entry + R×2
    tp2_sell_pct: float = 0.30     # sell 30%
    tp3_trailing_atr_mult: float = 1.5  # trailing ATR×1.5 for remaining 40%


class ExchangeGateway(Protocol):
    async def create_market_sell_order(self, symbol: str, amount: float, params: dict) -> dict: ...
    async def create_market_buy_order(self, symbol: str, amount: float, params: dict) -> dict: ...


@dataclass
class TPState:
    """Track take-profit state for one position."""
    symbol: str
    direction: str  # "long" or "short"
    entry_price: float
    initial_amount: float
    remaining_amount: float
    risk_per_unit: float  # R = distance from entry to initial stop
    atr: float

    # TP levels
    tp1_price: float = 0.0
    tp2_price: float = 0.0

    # Tracking
    current_stage: TPStage = TPStage.NONE
    tp1_hit: bool = False
    tp2_hit: bool = False
    tp3_active: bool = False
    tp3_trailing_stop: float = 0.0
    highest_since_tp2: float = 0.0

    # Filled quantities
    tp1_filled_qty: float = 0.0
    tp2_filled_qty: float = 0.0
    tp3_filled_qty: float = 0.0


class ProfitLock:
    """3-stage take-profit manager."""

    def __init__(
        self,
        config: Optional[ProfitLockConfig] = None,
        exchange: Optional[ExchangeGateway] = None,
        stop_loss_update_fn=None,
    ) -> None:
        self.config = config or ProfitLockConfig()
        self.exchange = exchange
        # Callback: (symbol, new_stop_price) -> coroutine to update SL
        self._sl_update_fn = stop_loss_update_fn
        self._positions: dict[str, TPState] = {}
        logger.info(
            "ProfitLock initialised | TP1=R×{} ({}%), TP2=R×{} ({}%), TP3=trailing ATR×{}",
            self.config.tp1_r_mult, int(self.config.tp1_sell_pct * 100),
            self.config.tp2_r_mult, int(self.config.tp2_sell_pct * 100),
            self.config.tp3_trailing_atr_mult,
        )

    # ── public API ──────────────────────────────────────────

    def register_position(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        amount: float,
        stop_price: float,
        atr: float,
    ) -> TPState:
        """Register a position for take-profit tracking."""
        is_long = direction == "long"
        risk = abs(entry_price - stop_price)

        if is_long:
            tp1 = entry_price + risk * self.config.tp1_r_mult
            tp2 = entry_price + risk * self.config.tp2_r_mult
        else:
            tp1 = entry_price - risk * self.config.tp1_r_mult
            tp2 = entry_price - risk * self.config.tp2_r_mult

        state = TPState(
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            initial_amount=amount,
            remaining_amount=amount,
            risk_per_unit=risk,
            atr=atr,
            tp1_price=tp1,
            tp2_price=tp2,
            highest_since_tp2=entry_price,
        )
        self._positions[symbol] = state

        logger.info(
            "TP registered | {} {} @ {:.4f} | R={:.4f} TP1={:.4f} TP2={:.4f}",
            symbol, direction, entry_price, risk, tp1, tp2,
        )
        return state

    async def update_price(self, symbol: str, current_price: float) -> Optional[dict]:
        """Check price against TP levels and execute partial exits.

        Returns dict with action taken, or None.
        """
        state = self._positions.get(symbol)
        if not state:
            return None

        is_long = state.direction == "long"
        actions: list[dict] = []

        # TP1 check
        if not state.tp1_hit:
            hit = (current_price >= state.tp1_price) if is_long else (current_price <= state.tp1_price)
            if hit:
                qty = state.initial_amount * self.config.tp1_sell_pct
                await self._execute_exit(state, qty, "TP1")
                state.tp1_hit = True
                state.tp1_filled_qty = qty
                state.remaining_amount -= qty
                state.current_stage = TPStage.TP1
                # Move SL to entry (breakeven)
                if self._sl_update_fn:
                    await self._sl_update_fn(symbol, state.entry_price)
                actions.append({"stage": "TP1", "qty": qty, "price": current_price})
                logger.info("TP1 HIT | {} @ {:.4f} | sold {:.6f} | SL -> breakeven", symbol, current_price, qty)

        # TP2 check
        if state.tp1_hit and not state.tp2_hit:
            hit = (current_price >= state.tp2_price) if is_long else (current_price <= state.tp2_price)
            if hit:
                qty = state.initial_amount * self.config.tp2_sell_pct
                qty = min(qty, state.remaining_amount)
                await self._execute_exit(state, qty, "TP2")
                state.tp2_hit = True
                state.tp2_filled_qty = qty
                state.remaining_amount -= qty
                state.current_stage = TPStage.TP2
                state.tp3_active = True
                state.highest_since_tp2 = current_price
                actions.append({"stage": "TP2", "qty": qty, "price": current_price})
                logger.info("TP2 HIT | {} @ {:.4f} | sold {:.6f} | trailing activated", symbol, current_price, qty)

        # TP3 trailing
        if state.tp3_active and state.remaining_amount > 0:
            if is_long:
                if current_price > state.highest_since_tp2:
                    state.highest_since_tp2 = current_price
                state.tp3_trailing_stop = state.highest_since_tp2 - state.atr * self.config.tp3_trailing_atr_mult

                if current_price <= state.tp3_trailing_stop:
                    qty = state.remaining_amount
                    await self._execute_exit(state, qty, "TP3")
                    state.tp3_filled_qty = qty
                    state.remaining_amount = 0
                    state.current_stage = TPStage.TP3
                    actions.append({"stage": "TP3", "qty": qty, "price": current_price})
                    logger.info("TP3 TRAILING EXIT | {} @ {:.4f} | sold {:.6f}", symbol, current_price, qty)
            else:
                if current_price < state.highest_since_tp2:
                    state.highest_since_tp2 = current_price
                state.tp3_trailing_stop = state.highest_since_tp2 + state.atr * self.config.tp3_trailing_atr_mult

                if current_price >= state.tp3_trailing_stop:
                    qty = state.remaining_amount
                    await self._execute_exit(state, qty, "TP3")
                    state.tp3_filled_qty = qty
                    state.remaining_amount = 0
                    state.current_stage = TPStage.TP3
                    actions.append({"stage": "TP3", "qty": qty, "price": current_price})
                    logger.info("TP3 TRAILING EXIT | {} @ {:.4f} | covered {:.6f}", symbol, current_price, qty)

        if state.remaining_amount <= 0:
            self._positions.pop(symbol, None)

        return {"symbol": symbol, "actions": actions} if actions else None

    def get_state(self, symbol: str) -> Optional[TPState]:
        return self._positions.get(symbol)

    def remove_position(self, symbol: str) -> None:
        self._positions.pop(symbol, None)

    # ── internals ───────────────────────────────────────────

    async def _execute_exit(self, state: TPState, qty: float, label: str) -> None:
        if not self.exchange or qty <= 0:
            return
        try:
            if state.direction == "long":
                await self.exchange.create_market_sell_order(state.symbol, qty, {"label": label})
            else:
                await self.exchange.create_market_buy_order(state.symbol, qty, {"label": label})
        except Exception as e:
            logger.error("Failed to execute {} exit for {}: {}", label, state.symbol, e)
