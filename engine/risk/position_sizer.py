"""Position sizer – Half-Kelly x ATR hybrid with regime & streak adjustments."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from loguru import logger


@dataclass
class SizerConfig:
    max_position_pct: float = 0.15       # hard cap 15%
    risk_per_trade_pct: float = 0.02     # 2% risk
    stop_multiplier: float = 2.0         # ATR × 2.0
    kelly_lookback: int = 50             # last N trades
    min_order_usd: float = 10.0          # exchange minimum
    max_min_order_usd: float = 20.0      # some exchanges require $20


@dataclass
class TradeRecord:
    pnl: float
    is_win: bool


class PositionSizer:
    """Compute position size using Half-Kelly × ATR hybrid with adjustments."""

    def __init__(self, config: Optional[SizerConfig] = None) -> None:
        self.config = config or SizerConfig()
        self._trade_history: list[TradeRecord] = []
        logger.info(
            "PositionSizer initialised | max={:.0%} kelly_lookback={} risk_pct={:.1%}",
            self.config.max_position_pct,
            self.config.kelly_lookback,
            self.config.risk_per_trade_pct,
        )

    # ── public API ──────────────────────────────────────────

    def record_trade(self, pnl: float) -> None:
        self._trade_history.append(TradeRecord(pnl=pnl, is_win=pnl > 0))

    def calculate(
        self,
        capital: float,
        atr: float,
        entry_price: float,
        regime: str = "SIDEWAYS",
        fear_greed_index: float = 50.0,
        streak: Optional[int] = None,
    ) -> dict:
        """Return position size in quote currency (USDT) and metadata.

        Args:
            capital: Total portfolio equity.
            atr: Current ATR value for the asset.
            entry_price: Expected entry price.
            regime: Market regime – "BULL", "SIDEWAYS", "BEAR".
            fear_greed_index: 0-100 Fear & Greed index.
            streak: Positive = consecutive wins, negative = consecutive losses.
                    If None, computed from trade history.
        """
        if capital <= 0 or atr <= 0 or entry_price <= 0:
            return self._min_result(capital, "invalid inputs")

        # 1. Half-Kelly size (as fraction of capital)
        kelly_frac = self._half_kelly()

        # 2. ATR-based size
        atr_size_usd = (capital * self.config.risk_per_trade_pct) / (atr * self.config.stop_multiplier)
        atr_frac = (atr_size_usd * entry_price) / capital if capital > 0 else 0.0
        # atr_size_usd is in units; convert to capital fraction
        atr_frac = min(atr_size_usd / (capital / entry_price), 1.0) if capital > 0 else 0.0
        # Simpler: fraction of capital
        atr_capital_frac = (capital * self.config.risk_per_trade_pct) / (atr * self.config.stop_multiplier * entry_price)
        atr_capital_frac = max(0.0, atr_capital_frac)

        # 3. Take minimum
        base_frac = min(kelly_frac, atr_capital_frac) if kelly_frac > 0 else atr_capital_frac

        # 4. Apply adjustments
        adj, adj_reasons = self._adjustments(regime, fear_greed_index, streak)
        adjusted_frac = base_frac * adj

        # 5. Cap at max
        final_frac = min(adjusted_frac, self.config.max_position_pct)
        final_usd = final_frac * capital

        # 6. Floor at exchange minimum
        if final_usd < self.config.min_order_usd:
            if capital >= self.config.min_order_usd:
                final_usd = self.config.min_order_usd
                final_frac = final_usd / capital
            else:
                return self._min_result(capital, "insufficient capital")

        result = {
            "size_usd": round(final_usd, 2),
            "size_frac": round(final_frac, 6),
            "size_qty": round(final_usd / entry_price, 8),
            "kelly_frac": round(kelly_frac, 6),
            "atr_frac": round(atr_capital_frac, 6),
            "adjustment_factor": round(adj, 4),
            "adjustment_reasons": adj_reasons,
            "capped": adjusted_frac > self.config.max_position_pct,
        }
        logger.debug("PositionSizer | {}", result)
        return result

    # ── Half-Kelly ──────────────────────────────────────────

    def _half_kelly(self) -> float:
        """Half-Kelly fraction from recent trade history."""
        trades = self._trade_history[-self.config.kelly_lookback:]
        if len(trades) < 10:
            return 0.0  # not enough data, fall back to ATR only

        wins = [t for t in trades if t.is_win]
        losses = [t for t in trades if not t.is_win]
        if not losses or not wins:
            return 0.0

        win_rate = len(wins) / len(trades)
        avg_win = sum(t.pnl for t in wins) / len(wins)
        avg_loss = abs(sum(t.pnl for t in losses) / len(losses))
        if avg_loss == 0:
            return 0.0

        rr_ratio = avg_win / avg_loss
        kelly = win_rate - (1 - win_rate) / rr_ratio
        half_kelly = max(0.0, kelly / 2.0)
        return half_kelly

    # ── Adjustments ─────────────────────────────────────────

    def _adjustments(
        self, regime: str, fear_greed: float, streak: Optional[int]
    ) -> tuple[float, list[str]]:
        factor = 1.0
        reasons: list[str] = []

        # Streak
        if streak is None:
            streak = self._compute_streak()

        if streak >= 3:
            factor *= 1.10
            reasons.append(f"win_streak({streak}): +10%")
        elif streak <= -2:
            factor *= 0.80
            reasons.append(f"loss_streak({streak}): -20%")

        # Regime
        if regime.upper() == "BEAR":
            factor *= 0.50
            reasons.append("BEAR regime: -50%")

        # Fear & Greed
        if fear_greed > 80:
            factor *= 0.70
            reasons.append(f"F&G={fear_greed}: -30%")

        return factor, reasons

    def _compute_streak(self) -> int:
        """Positive = consecutive wins, negative = consecutive losses."""
        if not self._trade_history:
            return 0
        streak = 0
        last_win = self._trade_history[-1].is_win
        for t in reversed(self._trade_history):
            if t.is_win == last_win:
                streak += 1
            else:
                break
        return streak if last_win else -streak

    def _min_result(self, capital: float, reason: str) -> dict:
        return {
            "size_usd": min(self.config.min_order_usd, capital),
            "size_frac": 0.0,
            "size_qty": 0.0,
            "kelly_frac": 0.0,
            "atr_frac": 0.0,
            "adjustment_factor": 1.0,
            "adjustment_reasons": [reason],
            "capped": False,
        }
