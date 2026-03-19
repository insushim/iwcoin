"""Drawdown guardian – halts trading when drawdown limits are breached."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from loguru import logger


class DrawdownLevel(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    TOTAL = "total"


@dataclass
class DrawdownLimits:
    daily_pct: float = 0.05       # -5%
    weekly_pct: float = 0.10      # -10%
    total_pct: float = 0.20       # -20%
    daily_cooldown_sec: int = 3600        # 1 hour
    weekly_cooldown_sec: int = 14400      # 4 hours
    total_cooldown_sec: int = 86400       # 24 hours (manual override expected)


@dataclass
class EquitySnapshot:
    timestamp: float
    equity: float


class DrawdownGuard:
    """Track daily / weekly / total drawdown and halt trading when limits are exceeded."""

    def __init__(self, initial_equity: float, limits: Optional[DrawdownLimits] = None) -> None:
        self.limits = limits or DrawdownLimits()
        self.initial_equity = initial_equity
        self.peak_equity = initial_equity
        self.current_equity = initial_equity

        # Rolling windows
        self._daily_peak: float = initial_equity
        self._weekly_peak: float = initial_equity
        self._daily_reset_ts: float = self._next_day_reset()
        self._weekly_reset_ts: float = self._next_week_reset()

        # Halt state: level -> resume_after_ts
        self._halts: dict[DrawdownLevel, float] = {}

        logger.info(
            "DrawdownGuard initialised | equity={:.2f} | limits D={:.1%} W={:.1%} T={:.1%}",
            initial_equity,
            self.limits.daily_pct,
            self.limits.weekly_pct,
            self.limits.total_pct,
        )

    # ── public API ──────────────────────────────────────────

    def update_equity(self, equity: float) -> None:
        """Call after every trade or periodic mark-to-market."""
        now = time.time()
        self._maybe_reset_windows(now)
        self.current_equity = equity

        # Update peaks (peaks only go up)
        if equity > self.peak_equity:
            self.peak_equity = equity
        if equity > self._daily_peak:
            self._daily_peak = equity
        if equity > self._weekly_peak:
            self._weekly_peak = equity

        # Check drawdowns
        self._check_and_halt(DrawdownLevel.DAILY, self._daily_peak, equity, self.limits.daily_pct, self.limits.daily_cooldown_sec, now)
        self._check_and_halt(DrawdownLevel.WEEKLY, self._weekly_peak, equity, self.limits.weekly_pct, self.limits.weekly_cooldown_sec, now)
        self._check_and_halt(DrawdownLevel.TOTAL, self.peak_equity, equity, self.limits.total_pct, self.limits.total_cooldown_sec, now)

    def is_halted(self) -> bool:
        """Return True if any drawdown halt is active."""
        now = time.time()
        active = {lvl: ts for lvl, ts in self._halts.items() if ts > now}
        self._halts = active
        return len(active) > 0

    def halt_reason(self) -> Optional[str]:
        """Human-readable halt reason, or None."""
        now = time.time()
        reasons: list[str] = []
        for lvl, resume_ts in self._halts.items():
            if resume_ts > now:
                remaining = int(resume_ts - now)
                reasons.append(f"{lvl.value} drawdown limit hit (resume in {remaining}s)")
        return "; ".join(reasons) if reasons else None

    def get_drawdowns(self) -> dict[str, float]:
        """Current drawdown percentages."""
        return {
            "daily": self._dd_pct(self._daily_peak),
            "weekly": self._dd_pct(self._weekly_peak),
            "total": self._dd_pct(self.peak_equity),
        }

    def manual_resume(self, level: Optional[DrawdownLevel] = None) -> None:
        """Manually clear a halt."""
        if level:
            self._halts.pop(level, None)
            logger.info("Manual resume for {} drawdown halt", level.value)
        else:
            self._halts.clear()
            logger.info("Manual resume for ALL drawdown halts")

    # ── internals ───────────────────────────────────────────

    def _dd_pct(self, peak: float) -> float:
        if peak <= 0:
            return 0.0
        return max(0.0, (peak - self.current_equity) / peak)

    def _check_and_halt(
        self,
        level: DrawdownLevel,
        peak: float,
        equity: float,
        limit_pct: float,
        cooldown_sec: int,
        now: float,
    ) -> None:
        dd = self._dd_pct(peak)
        if dd >= limit_pct and level not in self._halts:
            self._halts[level] = now + cooldown_sec
            logger.warning(
                "DRAWDOWN HALT | {} | dd={:.2%} >= limit={:.2%} | cooldown={}s",
                level.value,
                dd,
                limit_pct,
                cooldown_sec,
            )

    def _maybe_reset_windows(self, now: float) -> None:
        if now >= self._daily_reset_ts:
            self._daily_peak = self.current_equity
            self._daily_reset_ts = self._next_day_reset()
            logger.debug("Daily drawdown window reset")
        if now >= self._weekly_reset_ts:
            self._weekly_peak = self.current_equity
            self._weekly_reset_ts = self._next_week_reset()
            logger.debug("Weekly drawdown window reset")

    @staticmethod
    def _next_day_reset() -> float:
        """Next UTC midnight."""
        import datetime as dt
        now = dt.datetime.now(dt.timezone.utc)
        tomorrow = (now + dt.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return tomorrow.timestamp()

    @staticmethod
    def _next_week_reset() -> float:
        """Next UTC Monday 00:00."""
        import datetime as dt
        now = dt.datetime.now(dt.timezone.utc)
        days_ahead = (7 - now.weekday()) % 7 or 7
        monday = (now + dt.timedelta(days=days_ahead)).replace(hour=0, minute=0, second=0, microsecond=0)
        return monday.timestamp()
