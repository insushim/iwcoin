"""Circuit breaker – pauses strategies after consecutive losses."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Coroutine, Optional

from loguru import logger


class BreakerState(str, Enum):
    OK = "ok"
    PAUSED = "paused"
    LOCKED = "locked"  # manual reset required


@dataclass
class BreakerConfig:
    pause_1_losses: int = 5
    pause_1_sec: int = 3600        # 1 hour
    pause_2_losses: int = 8
    pause_2_sec: int = 14400       # 4 hours
    lock_losses: int = 10          # manual reset


@dataclass
class _StrategyState:
    consecutive_losses: int = 0
    state: BreakerState = BreakerState.OK
    resume_ts: float = 0.0
    total_losses: int = 0
    total_wins: int = 0


class CircuitBreaker:
    """Per-strategy consecutive loss counter with tiered pauses and Telegram alerts."""

    def __init__(
        self,
        config: Optional[BreakerConfig] = None,
        telegram_send_fn: Optional[Callable[[str], Coroutine]] = None,
    ) -> None:
        self.config = config or BreakerConfig()
        self._strategies: dict[str, _StrategyState] = {}
        self._telegram_send = telegram_send_fn
        logger.info(
            "CircuitBreaker initialised | thresholds={}/{}/{} losses",
            self.config.pause_1_losses,
            self.config.pause_2_losses,
            self.config.lock_losses,
        )

    # ── public API ──────────────────────────────────────────

    def record_win(self, strategy: str) -> None:
        """Record a winning trade – resets consecutive loss counter."""
        s = self._get(strategy)
        s.consecutive_losses = 0
        s.total_wins += 1

    async def record_loss(self, strategy: str) -> None:
        """Record a losing trade – may trigger pause/lock."""
        s = self._get(strategy)
        s.consecutive_losses += 1
        s.total_losses += 1
        losses = s.consecutive_losses
        now = time.time()

        if losses >= self.config.lock_losses:
            s.state = BreakerState.LOCKED
            s.resume_ts = float("inf")
            msg = (
                f"🚨 CIRCUIT BREAKER LOCKED | {strategy} | "
                f"{losses} consecutive losses | Manual reset required"
            )
            logger.critical(msg)
            await self._alert(msg)

        elif losses >= self.config.pause_2_losses:
            s.state = BreakerState.PAUSED
            s.resume_ts = now + self.config.pause_2_sec
            msg = (
                f"⚠️ CIRCUIT BREAKER TIER-2 | {strategy} | "
                f"{losses} consecutive losses | Paused {self.config.pause_2_sec}s"
            )
            logger.warning(msg)
            await self._alert(msg)

        elif losses >= self.config.pause_1_losses:
            s.state = BreakerState.PAUSED
            s.resume_ts = now + self.config.pause_1_sec
            msg = (
                f"⚠️ CIRCUIT BREAKER TIER-1 | {strategy} | "
                f"{losses} consecutive losses | Paused {self.config.pause_1_sec}s"
            )
            logger.warning(msg)
            await self._alert(msg)

    def is_allowed(self, strategy: str) -> bool:
        """Check if a strategy is allowed to trade."""
        s = self._get(strategy)
        if s.state == BreakerState.OK:
            return True
        if s.state == BreakerState.LOCKED:
            return False
        # PAUSED – check if cooldown has elapsed
        if time.time() >= s.resume_ts:
            s.state = BreakerState.OK
            logger.info("CircuitBreaker auto-resumed for {}", strategy)
            return True
        return False

    def get_state(self, strategy: str) -> dict:
        s = self._get(strategy)
        now = time.time()
        remaining = max(0, int(s.resume_ts - now)) if s.resume_ts != float("inf") else None
        return {
            "strategy": strategy,
            "state": s.state.value,
            "consecutive_losses": s.consecutive_losses,
            "total_wins": s.total_wins,
            "total_losses": s.total_losses,
            "resume_in_sec": remaining,
        }

    def manual_reset(self, strategy: str) -> None:
        """Manually reset a locked circuit breaker."""
        s = self._get(strategy)
        s.consecutive_losses = 0
        s.state = BreakerState.OK
        s.resume_ts = 0.0
        logger.info("CircuitBreaker manually reset for {}", strategy)

    def manual_reset_all(self) -> None:
        for strat in list(self._strategies):
            self.manual_reset(strat)

    # ── internals ───────────────────────────────────────────

    def _get(self, strategy: str) -> _StrategyState:
        if strategy not in self._strategies:
            self._strategies[strategy] = _StrategyState()
        return self._strategies[strategy]

    async def _alert(self, message: str) -> None:
        if self._telegram_send:
            try:
                await self._telegram_send(message)
            except Exception as e:
                logger.error("Telegram alert failed: {}", e)
