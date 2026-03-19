"""Order execution with slippage protection, DRY_RUN, and stop-loss placement."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Optional

from loguru import logger

from engine.config import TradingConfig
from engine.core.exchange_manager import ExchangeManager
from engine.utils.constants import OrderType, Side, OrderStatus
from engine.utils.helpers import round_price, round_amount, now_utc


@dataclass
class Signal:
    symbol: str
    side: str           # "buy" / "sell"
    order_type: str     # "market" / "limit"
    amount: float       # base currency amount
    price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    exchange: Optional[str] = None
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionResult:
    success: bool
    order: Optional[dict[str, Any]] = None
    sl_order: Optional[dict[str, Any]] = None
    tp_order: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    timestamp: str = ""


class OrderExecutor:
    """Execute trading signals with slippage protection and retry."""

    def __init__(
        self,
        exchange_manager: ExchangeManager,
        config: TradingConfig,
    ) -> None:
        self._em = exchange_manager
        self._config = config

    async def execute_signal(self, signal: Signal) -> ExecutionResult:
        """Execute a trading signal. Returns ExecutionResult."""
        try:
            # Slippage check for limit orders
            if signal.order_type == OrderType.LIMIT and signal.price:
                ok = await self._check_slippage(signal)
                if not ok:
                    return ExecutionResult(
                        success=False,
                        error="Slippage exceeds maximum threshold",
                        timestamp=now_utc().isoformat(),
                    )

            # Place main order
            order = await self._place_order(signal)

            sl_order = None
            tp_order = None

            # Place stop-loss on exchange
            if signal.stop_loss and order.get("status") in ("filled", "open"):
                sl_order = await self._place_stop_loss(signal, order)

            # Place take-profit on exchange
            if signal.take_profit and order.get("status") in ("filled", "open"):
                tp_order = await self._place_take_profit(signal, order)

            return ExecutionResult(
                success=True,
                order=order,
                sl_order=sl_order,
                tp_order=tp_order,
                timestamp=now_utc().isoformat(),
            )

        except Exception as exc:
            logger.error("Order execution failed for {}: {}", signal.symbol, exc)
            return ExecutionResult(
                success=False,
                error=str(exc),
                timestamp=now_utc().isoformat(),
            )

    async def _place_order(self, signal: Signal) -> dict[str, Any]:
        """Place the main order with retry."""
        retries = self._config.retry_count
        backoff = self._config.retry_backoff_base
        last_exc: Optional[Exception] = None

        for attempt in range(1, retries + 1):
            try:
                result = await self._em.create_order(
                    symbol=signal.symbol,
                    order_type=signal.order_type,
                    side=signal.side,
                    amount=signal.amount,
                    price=signal.price,
                    params=signal.params,
                    exchange=signal.exchange,
                )
                logger.info(
                    "Order placed: {} {} {} amount={} price={} id={}",
                    signal.order_type, signal.side, signal.symbol,
                    signal.amount, signal.price, result.get("id"),
                )
                return result
            except Exception as exc:
                last_exc = exc
                if attempt < retries:
                    wait = backoff * (2 ** (attempt - 1))
                    logger.warning(
                        "Order attempt {}/{} failed, retrying in {:.1f}s: {}",
                        attempt, retries, wait, exc,
                    )
                    await asyncio.sleep(wait)
        raise last_exc  # type: ignore[misc]

    async def _place_stop_loss(
        self, signal: Signal, parent_order: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        """Place a stop-loss order on the exchange."""
        try:
            sl_side = "sell" if signal.side == "buy" else "buy"
            amount = parent_order.get("filled", signal.amount) or signal.amount

            result = await self._em.create_order(
                symbol=signal.symbol,
                order_type="stop_loss",
                side=sl_side,
                amount=amount,
                price=signal.stop_loss,
                params={"stopPrice": signal.stop_loss, **signal.params},
                exchange=signal.exchange,
            )
            logger.info(
                "Stop-loss placed for {} at {} id={}",
                signal.symbol, signal.stop_loss, result.get("id"),
            )
            return result
        except Exception as exc:
            logger.error("Failed to place stop-loss for {}: {}", signal.symbol, exc)
            return None

    async def _place_take_profit(
        self, signal: Signal, parent_order: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        """Place a take-profit order on the exchange."""
        try:
            tp_side = "sell" if signal.side == "buy" else "buy"
            amount = parent_order.get("filled", signal.amount) or signal.amount

            result = await self._em.create_order(
                symbol=signal.symbol,
                order_type="take_profit",
                side=tp_side,
                amount=amount,
                price=signal.take_profit,
                params={"stopPrice": signal.take_profit, **signal.params},
                exchange=signal.exchange,
            )
            logger.info(
                "Take-profit placed for {} at {} id={}",
                signal.symbol, signal.take_profit, result.get("id"),
            )
            return result
        except Exception as exc:
            logger.error("Failed to place take-profit for {}: {}", signal.symbol, exc)
            return None

    async def _check_slippage(self, signal: Signal) -> bool:
        """Check if current market price is within slippage tolerance."""
        try:
            ticker = await self._em.fetch_ticker(signal.symbol, signal.exchange)
            last_price = ticker.get("last", 0)
            if not last_price or not signal.price:
                return True

            slippage = abs(signal.price - last_price) / last_price
            max_slippage = self._config.max_slippage_pct

            if slippage > max_slippage:
                logger.warning(
                    "Slippage {:.4%} exceeds max {:.4%} for {} (price={}, market={})",
                    slippage, max_slippage, signal.symbol, signal.price, last_price,
                )
                return False
            return True
        except Exception as exc:
            logger.warning("Slippage check failed, proceeding: {}", exc)
            return True
