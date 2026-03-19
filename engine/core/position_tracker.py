"""Track open positions, monitor P/L, manage stop-loss / take-profit / trailing stop."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from loguru import logger

from engine.utils.constants import PositionStatus, Side
from engine.utils.helpers import (
    calculate_pnl,
    calculate_pnl_pct,
    now_utc,
)


@dataclass
class Position:
    id: str
    symbol: str
    side: str               # "long" / "short"
    entry_price: float
    amount: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    trailing_stop_pct: Optional[float] = None
    trailing_stop_price: Optional[float] = None
    highest_price: float = 0.0   # for trailing stop (long)
    lowest_price: float = float("inf")  # for trailing stop (short)
    status: str = PositionStatus.OPEN
    unrealised_pnl: float = 0.0
    unrealised_pnl_pct: float = 0.0
    exchange: Optional[str] = None
    sl_order_id: Optional[str] = None
    tp_order_id: Optional[str] = None
    opened_at: str = ""
    closed_at: Optional[str] = None
    close_price: Optional[float] = None
    realised_pnl: Optional[float] = None
    metadata: dict[str, Any] = field(default_factory=dict)


class PositionTracker:
    """Manages open positions and checks SL/TP/trailing-stop levels."""

    def __init__(self, trailing_stop_pct: float = 0.01) -> None:
        self._positions: dict[str, Position] = {}
        self._closed: list[Position] = []
        self._default_trailing_pct = trailing_stop_pct

    # ── Open / Close ──────────────────────────────────────────────────

    def open_position(
        self,
        position_id: str,
        symbol: str,
        side: str,
        entry_price: float,
        amount: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        trailing_stop_pct: Optional[float] = None,
        exchange: Optional[str] = None,
        sl_order_id: Optional[str] = None,
        tp_order_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> Position:
        pos = Position(
            id=position_id,
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            amount=amount,
            stop_loss=stop_loss,
            take_profit=take_profit,
            trailing_stop_pct=trailing_stop_pct or self._default_trailing_pct,
            highest_price=entry_price,
            lowest_price=entry_price,
            exchange=exchange,
            sl_order_id=sl_order_id,
            tp_order_id=tp_order_id,
            opened_at=now_utc().isoformat(),
            metadata=metadata or {},
        )
        self._positions[position_id] = pos
        logger.info(
            "Opened {} {} {} entry={} amount={} SL={} TP={}",
            position_id, side, symbol, entry_price, amount, stop_loss, take_profit,
        )
        return pos

    def close_position(
        self, position_id: str, close_price: float
    ) -> Optional[Position]:
        pos = self._positions.pop(position_id, None)
        if pos is None:
            logger.warning("Position {} not found", position_id)
            return None

        pos.status = PositionStatus.CLOSED
        pos.close_price = close_price
        pos.closed_at = now_utc().isoformat()
        pos.realised_pnl = calculate_pnl(pos.entry_price, close_price, pos.amount, pos.side)
        self._closed.append(pos)

        logger.info(
            "Closed {} PnL={:.4f} (entry={} close={})",
            position_id, pos.realised_pnl, pos.entry_price, close_price,
        )
        return pos

    # ── Update ────────────────────────────────────────────────────────

    def update(self, current_prices: dict[str, float]) -> list[dict[str, Any]]:
        """Update all open positions with current prices.

        Returns list of trigger events (stop_loss / take_profit / trailing_stop).
        """
        events: list[dict[str, Any]] = []

        for pos in list(self._positions.values()):
            price = current_prices.get(pos.symbol)
            if price is None:
                continue

            # Update P/L
            pos.unrealised_pnl = calculate_pnl(pos.entry_price, price, pos.amount, pos.side)
            pos.unrealised_pnl_pct = calculate_pnl_pct(pos.entry_price, price, pos.side)

            # Update trailing stop tracking prices
            if pos.side == Side.LONG:
                if price > pos.highest_price:
                    pos.highest_price = price
                    self._update_trailing_stop_long(pos)
            else:
                if price < pos.lowest_price:
                    pos.lowest_price = price
                    self._update_trailing_stop_short(pos)

            # Check triggers
            trigger = self._check_triggers(pos, price)
            if trigger:
                events.append(trigger)

        return events

    # ── Trailing Stop ─────────────────────────────────────────────────

    @staticmethod
    def _update_trailing_stop_long(pos: Position) -> None:
        if pos.trailing_stop_pct:
            pos.trailing_stop_price = pos.highest_price * (1 - pos.trailing_stop_pct)

    @staticmethod
    def _update_trailing_stop_short(pos: Position) -> None:
        if pos.trailing_stop_pct:
            pos.trailing_stop_price = pos.lowest_price * (1 + pos.trailing_stop_pct)

    # ── Trigger checks ────────────────────────────────────────────────

    @staticmethod
    def _check_triggers(pos: Position, price: float) -> Optional[dict[str, Any]]:
        is_long = pos.side == Side.LONG

        # Stop-loss
        if pos.stop_loss:
            if (is_long and price <= pos.stop_loss) or (not is_long and price >= pos.stop_loss):
                logger.warning(
                    "STOP-LOSS triggered for {} at {} (SL={})", pos.id, price, pos.stop_loss,
                )
                return {"type": "stop_loss", "position_id": pos.id, "price": price}

        # Take-profit
        if pos.take_profit:
            if (is_long and price >= pos.take_profit) or (not is_long and price <= pos.take_profit):
                logger.info(
                    "TAKE-PROFIT triggered for {} at {} (TP={})", pos.id, price, pos.take_profit,
                )
                return {"type": "take_profit", "position_id": pos.id, "price": price}

        # Trailing stop
        if pos.trailing_stop_price:
            if (is_long and price <= pos.trailing_stop_price) or (
                not is_long and price >= pos.trailing_stop_price
            ):
                logger.info(
                    "TRAILING-STOP triggered for {} at {} (trail={})",
                    pos.id, price, pos.trailing_stop_price,
                )
                return {"type": "trailing_stop", "position_id": pos.id, "price": price}

        return None

    # ── Queries ───────────────────────────────────────────────────────

    def get_position(self, position_id: str) -> Optional[Position]:
        return self._positions.get(position_id)

    @property
    def open_positions(self) -> list[Position]:
        return list(self._positions.values())

    @property
    def closed_positions(self) -> list[Position]:
        return list(self._closed)

    @property
    def open_count(self) -> int:
        return len(self._positions)

    def get_positions_for_symbol(self, symbol: str) -> list[Position]:
        return [p for p in self._positions.values() if p.symbol == symbol]

    def total_unrealised_pnl(self) -> float:
        return sum(p.unrealised_pnl for p in self._positions.values())
