"""Automatic trade journal with full context recording."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from loguru import logger

from engine.data.supabase_client import SupabaseClient


class TradeJournal:
    """Record every trade with regime, strategy, indicators, and signal context.

    Generates daily and weekly performance summaries.
    """

    def __init__(self, db: Optional[SupabaseClient] = None) -> None:
        self._db = db or SupabaseClient()
        self._local_trades: list[dict[str, Any]] = []

    def record_trade(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        exit_price: float,
        size: float,
        pnl: float,
        regime: str = "",
        strategy: str = "",
        signal_confidence: float = 0.0,
        indicators: Optional[dict[str, float]] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        reason: str = "",
        extra: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Record a completed trade with full context."""
        now = datetime.now(timezone.utc)
        entry = {
            "symbol": symbol,
            "side": side,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "size": size,
            "pnl": round(pnl, 4),
            "pnl_pct": round((exit_price / entry_price - 1) * 100 * (1 if side == "long" else -1), 4),
            "regime": regime,
            "strategy": strategy,
            "signal_confidence": round(signal_confidence, 4),
            "indicators": indicators or {},
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "reason": reason,
            "timestamp": now.isoformat(),
            **(extra or {}),
        }

        self._local_trades.append(entry)

        if self._db.is_connected:
            self._db.insert_trade(entry)

        logger.info(
            "Trade recorded: {} {} {} pnl={:.2f} ({}) [{}]",
            side, symbol, strategy, pnl, regime, reason,
        )
        return entry

    def daily_summary(self, date: Optional[datetime] = None) -> dict[str, Any]:
        """Generate summary for a specific date (default: today UTC)."""
        target = (date or datetime.now(timezone.utc)).date()
        trades = [
            t for t in self._local_trades
            if datetime.fromisoformat(t["timestamp"]).date() == target
        ]

        if not trades:
            return {"date": str(target), "n_trades": 0, "total_pnl": 0.0}

        pnls = [t["pnl"] for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]

        summary = {
            "date": str(target),
            "n_trades": len(trades),
            "total_pnl": round(sum(pnls), 2),
            "win_count": len(wins),
            "loss_count": len(losses),
            "win_rate_pct": round(len(wins) / len(trades) * 100, 1) if trades else 0.0,
            "avg_pnl": round(sum(pnls) / len(pnls), 2),
            "best_trade": round(max(pnls), 2),
            "worst_trade": round(min(pnls), 2),
            "strategies_used": list({t["strategy"] for t in trades if t["strategy"]}),
            "regimes_seen": list({t["regime"] for t in trades if t["regime"]}),
        }
        return summary

    def weekly_summary(self, end_date: Optional[datetime] = None) -> dict[str, Any]:
        """Generate summary for the last 7 days."""
        end = (end_date or datetime.now(timezone.utc)).date()
        start = end - timedelta(days=6)

        trades = [
            t for t in self._local_trades
            if start <= datetime.fromisoformat(t["timestamp"]).date() <= end
        ]

        if not trades:
            return {
                "period": f"{start} ~ {end}",
                "n_trades": 0,
                "total_pnl": 0.0,
            }

        pnls = [t["pnl"] for t in trades]
        wins = [p for p in pnls if p > 0]

        # Daily PnLs
        daily_pnls: dict[str, float] = {}
        for t in trades:
            d = datetime.fromisoformat(t["timestamp"]).strftime("%Y-%m-%d")
            daily_pnls[d] = daily_pnls.get(d, 0.0) + t["pnl"]

        # Strategy breakdown
        strategy_pnl: dict[str, float] = {}
        strategy_count: dict[str, int] = {}
        for t in trades:
            s = t.get("strategy", "unknown")
            strategy_pnl[s] = strategy_pnl.get(s, 0.0) + t["pnl"]
            strategy_count[s] = strategy_count.get(s, 0) + 1

        summary = {
            "period": f"{start} ~ {end}",
            "n_trades": len(trades),
            "total_pnl": round(sum(pnls), 2),
            "win_rate_pct": round(len(wins) / len(trades) * 100, 1) if trades else 0.0,
            "avg_pnl": round(sum(pnls) / len(pnls), 2),
            "best_day": max(daily_pnls.items(), key=lambda x: x[1]) if daily_pnls else None,
            "worst_day": min(daily_pnls.items(), key=lambda x: x[1]) if daily_pnls else None,
            "daily_pnls": {k: round(v, 2) for k, v in sorted(daily_pnls.items())},
            "strategy_breakdown": {
                s: {"pnl": round(strategy_pnl[s], 2), "count": strategy_count[s]}
                for s in strategy_pnl
            },
            "profitable_days": sum(1 for v in daily_pnls.values() if v > 0),
            "losing_days": sum(1 for v in daily_pnls.values() if v < 0),
        }
        return summary

    def get_recent_trades(self, n: int = 20) -> list[dict[str, Any]]:
        """Return the N most recent trades."""
        return self._local_trades[-n:]

    @property
    def trade_count(self) -> int:
        return len(self._local_trades)
