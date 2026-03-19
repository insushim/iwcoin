"""Central risk engine – orchestrates all risk checks before and after trades."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

from loguru import logger

from engine.risk.circuit_breaker import CircuitBreaker
from engine.risk.correlation_filter import CorrelationFilter
from engine.risk.drawdown_guard import DrawdownGuard


@dataclass
class RiskConfig:
    # Drawdown limits
    max_daily_drawdown_pct: float = 0.05
    max_weekly_drawdown_pct: float = 0.10
    max_total_drawdown_pct: float = 0.20
    # Position limits
    max_concurrent_positions: int = 5
    max_position_pct: float = 0.15       # 15% of capital
    # R/R minimum
    min_rr_ratio: float = 2.0
    # Daily trade limit
    max_daily_trades: int = 50
    # Spread check
    max_spread_pct: float = 0.005        # 0.5%


@dataclass
class Signal:
    """Incoming trade signal to be risk-checked."""
    symbol: str
    direction: str          # "long" or "short"
    strategy: str
    entry_price: float
    stop_loss: float
    take_profit: float
    spread_pct: float = 0.0
    atr: float = 0.0
    regime: str = "SIDEWAYS"


class RiskEngine:
    """Central pre-trade and post-trade risk management engine."""

    def __init__(
        self,
        initial_equity: float,
        config: Optional[RiskConfig] = None,
        drawdown_guard: Optional[DrawdownGuard] = None,
        circuit_breaker: Optional[CircuitBreaker] = None,
        correlation_filter: Optional[CorrelationFilter] = None,
    ) -> None:
        self.config = config or RiskConfig()
        self.equity = initial_equity

        # Sub-modules (create defaults if not injected)
        from engine.risk.drawdown_guard import DrawdownLimits
        self.drawdown = drawdown_guard or DrawdownGuard(
            initial_equity,
            DrawdownLimits(
                daily_pct=self.config.max_daily_drawdown_pct,
                weekly_pct=self.config.max_weekly_drawdown_pct,
                total_pct=self.config.max_total_drawdown_pct,
            ),
        )
        self.circuit_breaker = circuit_breaker or CircuitBreaker()
        self.correlation = correlation_filter or CorrelationFilter()

        # State tracking
        self._open_positions: dict[str, dict] = {}  # symbol -> position info
        self._daily_trade_count: int = 0
        self._daily_reset_ts: float = self._next_day_ts()

        logger.info(
            "RiskEngine initialised | equity={:.2f} | max_positions={} | min_rr={}",
            initial_equity, self.config.max_concurrent_positions, self.config.min_rr_ratio,
        )

    # ── pre-trade check ─────────────────────────────────────

    def pre_trade_check(self, signal: Signal, allocated_capital: float) -> dict:
        """Run all risk checks in order. Returns {"approved": bool, "reason": str}.

        Check order:
        1. Drawdown
        2. Circuit breaker
        3. Concurrent positions
        4. Correlation filter
        5. Position size
        6. R/R ratio
        7. Daily trade count
        8. Spread check
        """
        self._maybe_reset_daily()

        # 1. Drawdown
        if self.drawdown.is_halted():
            reason = self.drawdown.halt_reason() or "drawdown limit exceeded"
            return self._reject(f"DRAWDOWN: {reason}")

        # 2. Circuit breaker
        if not self.circuit_breaker.is_allowed(signal.strategy):
            state = self.circuit_breaker.get_state(signal.strategy)
            return self._reject(
                f"CIRCUIT_BREAKER: {signal.strategy} paused | "
                f"losses={state['consecutive_losses']} resume_in={state['resume_in_sec']}s"
            )

        # 3. Concurrent positions
        if len(self._open_positions) >= self.config.max_concurrent_positions:
            return self._reject(
                f"MAX_POSITIONS: {len(self._open_positions)}/{self.config.max_concurrent_positions}"
            )

        # 4. Correlation filter
        open_pos_list = [
            {
                "symbol": sym,
                "direction": p["direction"],
                "weight": p.get("weight", 1.0 / max(len(self._open_positions), 1)),
            }
            for sym, p in self._open_positions.items()
        ]
        corr_check = self.correlation.check_pair_entry(
            signal.symbol, signal.direction, open_pos_list
        )
        if not corr_check["approved"]:
            return self._reject(f"CORRELATION: {corr_check['reason']}")

        # Portfolio-level correlation
        if open_pos_list:
            test_positions = open_pos_list + [{
                "symbol": signal.symbol,
                "direction": signal.direction,
                "weight": 1.0 / (len(open_pos_list) + 1),
            }]
            port_check = self.correlation.check_portfolio(test_positions)
            if not port_check["approved"]:
                return self._reject(f"PORTFOLIO_CORRELATION: {port_check['reason']}")

        # 5. Position size
        if self.equity > 0:
            position_pct = allocated_capital / self.equity
            if position_pct > self.config.max_position_pct:
                return self._reject(
                    f"POSITION_SIZE: {position_pct:.1%} > max {self.config.max_position_pct:.1%}"
                )

        # 6. R/R ratio
        risk = abs(signal.entry_price - signal.stop_loss)
        reward = abs(signal.take_profit - signal.entry_price)
        if risk > 0:
            rr_ratio = reward / risk
            if rr_ratio < self.config.min_rr_ratio:
                return self._reject(
                    f"RR_RATIO: {rr_ratio:.2f} < min {self.config.min_rr_ratio}"
                )
        else:
            return self._reject("RR_RATIO: risk is zero (SL == entry)")

        # 7. Daily trade count
        if self._daily_trade_count >= self.config.max_daily_trades:
            return self._reject(
                f"DAILY_TRADES: {self._daily_trade_count}/{self.config.max_daily_trades}"
            )

        # 8. Spread check
        if signal.spread_pct > self.config.max_spread_pct:
            return self._reject(
                f"SPREAD: {signal.spread_pct:.3%} > max {self.config.max_spread_pct:.3%}"
            )

        logger.info("Risk APPROVED | {} {} {} | capital={:.2f}", signal.strategy, signal.symbol, signal.direction, allocated_capital)
        return {"approved": True, "reason": "all checks passed"}

    # ── post-trade update ───────────────────────────────────

    async def post_trade_update(
        self,
        symbol: str,
        direction: str,
        strategy: str,
        entry_price: float,
        amount: float,
        capital_used: float,
        is_open: bool = True,
        pnl: float = 0.0,
    ) -> None:
        """Update internal state after a trade is executed or closed."""
        if is_open:
            self._open_positions[symbol] = {
                "direction": direction,
                "strategy": strategy,
                "entry_price": entry_price,
                "amount": amount,
                "capital_used": capital_used,
                "opened_at": time.time(),
            }
            self._daily_trade_count += 1
            logger.debug("Position opened: {} {} {}", symbol, direction, strategy)
        else:
            self._open_positions.pop(symbol, None)
            self.equity += pnl
            self.drawdown.update_equity(self.equity)

            if pnl > 0:
                self.circuit_breaker.record_win(strategy)
            else:
                await self.circuit_breaker.record_loss(strategy)

            logger.debug("Position closed: {} | pnl={:.2f} | equity={:.2f}", symbol, pnl, self.equity)

    # ── portfolio check ─────────────────────────────────────

    def portfolio_check(self) -> dict:
        """Run portfolio-level risk checks. Returns status summary."""
        drawdowns = self.drawdown.get_drawdowns()
        halted = self.drawdown.is_halted()
        halt_reason = self.drawdown.halt_reason()

        breaker_states = {}
        strategies_seen = set()
        for pos in self._open_positions.values():
            s = pos["strategy"]
            if s not in strategies_seen:
                strategies_seen.add(s)
                breaker_states[s] = self.circuit_breaker.get_state(s)

        open_pos_list = [
            {"symbol": sym, "weight": 1.0 / max(len(self._open_positions), 1)}
            for sym in self._open_positions
        ]
        port_corr = self.correlation.portfolio_correlation(open_pos_list) if len(open_pos_list) >= 2 else 0.0

        return {
            "equity": round(self.equity, 2),
            "open_positions": len(self._open_positions),
            "daily_trades": self._daily_trade_count,
            "drawdowns": {k: round(v, 4) for k, v in drawdowns.items()},
            "halted": halted,
            "halt_reason": halt_reason,
            "circuit_breakers": breaker_states,
            "portfolio_correlation": round(port_corr, 4),
        }

    # ── helpers ─────────────────────────────────────────────

    def update_equity(self, equity: float) -> None:
        self.equity = equity
        self.drawdown.update_equity(equity)

    def get_open_positions(self) -> dict[str, dict]:
        return dict(self._open_positions)

    @staticmethod
    def _reject(reason: str) -> dict:
        logger.warning("Risk REJECTED | {}", reason)
        return {"approved": False, "reason": reason}

    def _maybe_reset_daily(self) -> None:
        now = time.time()
        if now >= self._daily_reset_ts:
            self._daily_trade_count = 0
            self._daily_reset_ts = self._next_day_ts()

    @staticmethod
    def _next_day_ts() -> float:
        import datetime as dt
        now = dt.datetime.now(dt.timezone.utc)
        tomorrow = (now + dt.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return tomorrow.timestamp()
