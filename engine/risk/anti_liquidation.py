"""Anti-liquidation monitor – auto-reduces futures positions to avoid liquidation."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Optional, Protocol

from loguru import logger


@dataclass
class AntiLiqConfig:
    poll_interval_sec: float = 30.0
    margin_warn_pct: float = 30.0      # auto-reduce at <30%
    margin_danger_pct: float = 20.0    # aggressive reduce at <20%
    margin_critical_pct: float = 15.0  # force close at <15%
    reduce_warn_pct: float = 0.25      # reduce 25% of position
    reduce_danger_pct: float = 0.50    # reduce 50% of position
    max_leverage_bear: int = 1
    high_atr_threshold: float = 0.05   # ATR/price > 5% = high volatility
    max_leverage_high_atr: int = 1


class ExchangeGateway(Protocol):
    async def fetch_positions(self, symbols: Optional[list[str]] = None) -> list[dict]: ...
    async def fetch_balance(self) -> dict: ...
    async def create_market_sell_order(self, symbol: str, amount: float, params: dict) -> dict: ...
    async def create_market_buy_order(self, symbol: str, amount: float, params: dict) -> dict: ...
    async def set_leverage(self, symbol: str, leverage: int, params: dict) -> dict: ...
    async def set_margin_mode(self, symbol: str, mode: str, params: dict) -> dict: ...


@dataclass
class FuturesPosition:
    symbol: str
    side: str  # "long" or "short"
    amount: float
    entry_price: float
    mark_price: float
    leverage: int
    margin_ratio: float  # percentage 0-100
    unrealised_pnl: float
    isolated: bool


class AntiLiquidation:
    """Monitor margin ratios and auto-reduce positions to prevent liquidation."""

    def __init__(
        self,
        config: Optional[AntiLiqConfig] = None,
        exchange: Optional[ExchangeGateway] = None,
        telegram_send_fn=None,
    ) -> None:
        self.config = config or AntiLiqConfig()
        self.exchange = exchange
        self._telegram_send = telegram_send_fn
        self._running = False
        self._task: Optional[asyncio.Task] = None
        logger.info(
            "AntiLiquidation initialised | poll={}s | thresholds={}/{}/{}%",
            self.config.poll_interval_sec,
            self.config.margin_warn_pct,
            self.config.margin_danger_pct,
            self.config.margin_critical_pct,
        )

    # ── lifecycle ───────────────────────────────────────────

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("AntiLiquidation monitor started")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("AntiLiquidation monitor stopped")

    # ── one-shot check (for external callers) ───────────────

    async def check_positions(
        self,
        positions: Optional[list[FuturesPosition]] = None,
    ) -> list[dict]:
        """Check all futures positions and return actions taken."""
        if not self.exchange:
            return []

        if positions is None:
            positions = await self._fetch_positions()

        actions: list[dict] = []
        for pos in positions:
            action = await self._evaluate_position(pos)
            if action:
                actions.append(action)
        return actions

    async def enforce_leverage(
        self,
        symbol: str,
        desired_leverage: int,
        regime: str = "SIDEWAYS",
        atr_ratio: float = 0.0,
    ) -> int:
        """Force leverage to 1x in BEAR regime or high ATR. Enforce isolated margin.

        Returns the actual leverage set.
        """
        if not self.exchange:
            return desired_leverage

        # Force 1x in BEAR or high volatility
        if regime.upper() == "BEAR":
            desired_leverage = min(desired_leverage, self.config.max_leverage_bear)
            logger.info("{} leverage forced to {}x (BEAR regime)", symbol, desired_leverage)
        if atr_ratio > self.config.high_atr_threshold:
            desired_leverage = min(desired_leverage, self.config.max_leverage_high_atr)
            logger.info("{} leverage forced to {}x (high ATR={:.2%})", symbol, desired_leverage, atr_ratio)

        try:
            # Always use isolated margin
            await self.exchange.set_margin_mode(symbol, "isolated", {})
            await self.exchange.set_leverage(symbol, desired_leverage, {})
        except Exception as e:
            logger.error("Failed to set leverage/margin for {}: {}", symbol, e)

        return desired_leverage

    # ── monitor loop ────────────────────────────────────────

    async def _monitor_loop(self) -> None:
        while self._running:
            try:
                positions = await self._fetch_positions()
                for pos in positions:
                    await self._evaluate_position(pos)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("AntiLiquidation monitor error: {}", e)

            await asyncio.sleep(self.config.poll_interval_sec)

    async def _evaluate_position(self, pos: FuturesPosition) -> Optional[dict]:
        """Evaluate a single position and take action if needed."""
        mr = pos.margin_ratio

        if mr < self.config.margin_critical_pct:
            # Force close entire position
            await self._reduce_position(pos, 1.0)
            msg = (
                f"🚨 FORCE CLOSE | {pos.symbol} {pos.side} | "
                f"margin_ratio={mr:.1f}% < {self.config.margin_critical_pct}%"
            )
            logger.critical(msg)
            await self._alert(msg)
            return {"symbol": pos.symbol, "action": "force_close", "margin_ratio": mr}

        elif mr < self.config.margin_danger_pct:
            await self._reduce_position(pos, self.config.reduce_danger_pct)
            msg = (
                f"⚠️ DANGER REDUCE | {pos.symbol} {pos.side} | "
                f"margin_ratio={mr:.1f}% | reduced {self.config.reduce_danger_pct:.0%}"
            )
            logger.warning(msg)
            await self._alert(msg)
            return {"symbol": pos.symbol, "action": "danger_reduce", "margin_ratio": mr}

        elif mr < self.config.margin_warn_pct:
            await self._reduce_position(pos, self.config.reduce_warn_pct)
            msg = (
                f"⚠️ WARN REDUCE | {pos.symbol} {pos.side} | "
                f"margin_ratio={mr:.1f}% | reduced {self.config.reduce_warn_pct:.0%}"
            )
            logger.warning(msg)
            await self._alert(msg)
            return {"symbol": pos.symbol, "action": "warn_reduce", "margin_ratio": mr}

        return None

    async def _reduce_position(self, pos: FuturesPosition, fraction: float) -> None:
        if not self.exchange:
            return
        reduce_amount = pos.amount * fraction
        try:
            if pos.side == "long":
                await self.exchange.create_market_sell_order(
                    pos.symbol, reduce_amount, {"reduceOnly": True}
                )
            else:
                await self.exchange.create_market_buy_order(
                    pos.symbol, reduce_amount, {"reduceOnly": True}
                )
            logger.info("Reduced {} {} by {:.4f} ({:.0%})", pos.symbol, pos.side, reduce_amount, fraction)
        except Exception as e:
            logger.error("Failed to reduce {} position: {}", pos.symbol, e)

    async def _fetch_positions(self) -> list[FuturesPosition]:
        """Fetch open futures positions from exchange."""
        if not self.exchange:
            return []
        try:
            raw = await self.exchange.fetch_positions()
            positions: list[FuturesPosition] = []
            for p in raw:
                amount = abs(float(p.get("contracts", 0) or p.get("amount", 0)))
                if amount == 0:
                    continue
                positions.append(FuturesPosition(
                    symbol=p.get("symbol", ""),
                    side=p.get("side", "long"),
                    amount=amount,
                    entry_price=float(p.get("entryPrice", 0)),
                    mark_price=float(p.get("markPrice", 0)),
                    leverage=int(p.get("leverage", 1)),
                    margin_ratio=float(p.get("marginRatio", 100)),
                    unrealised_pnl=float(p.get("unrealizedPnl", 0)),
                    isolated=p.get("marginMode", "isolated") == "isolated",
                ))
            return positions
        except Exception as e:
            logger.error("Failed to fetch positions: {}", e)
            return []

    async def _alert(self, message: str) -> None:
        if self._telegram_send:
            try:
                await self._telegram_send(message)
            except Exception as e:
                logger.error("Telegram alert failed: {}", e)
