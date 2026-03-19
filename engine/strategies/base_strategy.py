"""Abstract base class for all trading strategies."""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from loguru import logger

from engine.config import TradingConfig
from engine.utils.constants import Side


# ── Signal data ──────────────────────────────────────────────────────────────

@dataclass
class Signal:
    """Represents a trading signal emitted by a strategy."""

    symbol: str
    side: Side
    confidence: float  # 0.0 – 1.0
    strategy_name: str
    reason: str = ""
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    size_multiplier: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


# ── Performance tracker ──────────────────────────────────────────────────────

@dataclass
class PerformanceStats:
    total_signals: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    win_rate: float = 0.0
    avg_rr_ratio: float = 0.0

    def update_win_rate(self) -> None:
        total = self.winning_trades + self.losing_trades
        self.win_rate = self.winning_trades / total if total > 0 else 0.0


# ── Base strategy ────────────────────────────────────────────────────────────

class BaseStrategy(ABC):
    """Abstract base for every strategy.

    Subclasses must implement ``generate_signal``.
    The ``run_cycle`` method orchestrates: signal → risk check → R/R check → execute.
    """

    name: str = "base"

    def __init__(
        self,
        config: TradingConfig,
        exchange: Any,
        executor: Any,
        positions: Any,
        risk: Any,
        db: Any = None,
        telegram: Any = None,
    ) -> None:
        self.config = config
        self.exchange = exchange
        self.executor = executor
        self.positions = positions
        self.risk = risk
        self.db = db
        self.telegram = telegram

        self._running = False
        self._cycle_interval: float = 60.0  # seconds between cycles
        self.performance = PerformanceStats()

    # ── Abstract ─────────────────────────────────────────────────────────

    @abstractmethod
    async def generate_signal(self, symbol: str) -> Optional[Signal]:
        """Analyse market data and return a Signal or None."""
        ...

    # ── Core loop ────────────────────────────────────────────────────────

    async def run_cycle(self, symbol: str) -> Optional[Signal]:
        """Single strategy cycle: signal → risk → R/R → execute."""
        try:
            signal = await self.generate_signal(symbol)
            if signal is None:
                return None

            self.performance.total_signals += 1

            # Risk check
            if not await self._check_risk(signal):
                logger.info(
                    "[{}] Signal rejected by risk manager: {} {}",
                    self.name, signal.side.value, signal.symbol,
                )
                return None

            # Reward/Risk ratio check
            if not self._check_rr_ratio(signal):
                logger.info(
                    "[{}] Signal rejected by R/R filter: {} {}",
                    self.name, signal.side.value, signal.symbol,
                )
                return None

            # Execute
            await self._execute(signal)
            return signal

        except Exception:
            logger.exception("[{}] run_cycle error for {}", self.name, symbol)
            return None

    async def start(
        self,
        symbols: list[str],
        interval: Optional[float] = None,
    ) -> None:
        """Start the strategy loop for the given symbols."""
        self._running = True
        cycle_interval = interval or self._cycle_interval
        logger.info("[{}] Strategy started – symbols={}", self.name, symbols)

        while self._running:
            for symbol in symbols:
                if not self._running:
                    break
                await self.run_cycle(symbol)
            await asyncio.sleep(cycle_interval)

    def stop(self) -> None:
        """Gracefully stop the strategy loop."""
        logger.info("[{}] Strategy stopping", self.name)
        self._running = False

    # ── Risk & R/R helpers ───────────────────────────────────────────────

    async def _check_risk(self, signal: Signal) -> bool:
        """Delegate to the risk manager. Returns True if allowed."""
        if self.risk is None:
            return True
        try:
            if asyncio.iscoroutinefunction(getattr(self.risk, "check", None)):
                return await self.risk.check(signal)
            return self.risk.check(signal)
        except Exception:
            logger.exception("[{}] Risk check error", self.name)
            return False

    def _check_rr_ratio(self, signal: Signal, min_rr: float = 1.5) -> bool:
        """Verify the reward-to-risk ratio meets the minimum threshold."""
        if signal.entry_price is None:
            return True  # no price info → skip check
        if signal.stop_loss is None or signal.take_profit is None:
            return True

        risk_dist = abs(signal.entry_price - signal.stop_loss)
        reward_dist = abs(signal.take_profit - signal.entry_price)

        if risk_dist == 0:
            return False
        return (reward_dist / risk_dist) >= min_rr

    # ── Execution ────────────────────────────────────────────────────────

    async def _execute(self, signal: Signal) -> None:
        """Forward the signal to the executor and notify via Telegram."""
        try:
            if self.executor is not None:
                if asyncio.iscoroutinefunction(getattr(self.executor, "execute", None)):
                    await self.executor.execute(signal)
                else:
                    self.executor.execute(signal)

            logger.info(
                "[{}] Executed {} {} conf={:.2f}",
                self.name, signal.side.value, signal.symbol, signal.confidence,
            )

            if self.telegram is not None:
                await self._notify(signal)

        except Exception:
            logger.exception("[{}] Execution error", self.name)

    async def _notify(self, signal: Signal) -> None:
        msg = (
            f"📊 [{self.name}] {signal.side.value.upper()} {signal.symbol}\n"
            f"Confidence: {signal.confidence:.0%}\n"
            f"Reason: {signal.reason}"
        )
        try:
            if asyncio.iscoroutinefunction(getattr(self.telegram, "send", None)):
                await self.telegram.send(msg)
            else:
                self.telegram.send(msg)
        except Exception:
            logger.warning("[{}] Telegram notification failed", self.name)

    # ── Performance ──────────────────────────────────────────────────────

    def record_trade(self, pnl: float) -> None:
        if pnl >= 0:
            self.performance.winning_trades += 1
        else:
            self.performance.losing_trades += 1
        self.performance.total_pnl += pnl
        self.performance.update_win_rate()

    def get_performance(self) -> dict[str, Any]:
        p = self.performance
        return {
            "strategy": self.name,
            "total_signals": p.total_signals,
            "winning": p.winning_trades,
            "losing": p.losing_trades,
            "win_rate": round(p.win_rate, 4),
            "total_pnl": round(p.total_pnl, 2),
            "max_drawdown": round(p.max_drawdown, 4),
            "sharpe_ratio": round(p.sharpe_ratio, 4),
            "avg_rr_ratio": round(p.avg_rr_ratio, 4),
        }
