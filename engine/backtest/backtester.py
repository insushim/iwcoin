"""Event-driven backtester with fee/slippage simulation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional

import numpy as np
import pandas as pd
from loguru import logger


@dataclass
class Trade:
    """Single completed trade."""

    entry_time: datetime
    exit_time: datetime
    side: str  # "long" or "short"
    entry_price: float
    exit_price: float
    size: float
    pnl: float
    pnl_pct: float
    fees: float
    slippage_cost: float
    reason: str = ""  # "tp", "sl", "signal", "forced"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BacktestResult:
    """Complete backtest output."""

    trades: list[Trade]
    equity_curve: pd.Series
    initial_capital: float
    final_capital: float
    total_return_pct: float
    n_trades: int
    start_date: datetime
    end_date: datetime
    metrics: dict[str, float] = field(default_factory=dict)


class Backtester:
    """Run a strategy on historical data with realistic execution simulation.

    Fees: 0.1% per trade (maker/taker average).
    Slippage: 0.05% per trade.
    """

    DEFAULT_FEE_PCT = 0.001  # 0.1%
    DEFAULT_SLIPPAGE_PCT = 0.0005  # 0.05%

    def __init__(
        self,
        initial_capital: float = 10_000.0,
        fee_pct: float = DEFAULT_FEE_PCT,
        slippage_pct: float = DEFAULT_SLIPPAGE_PCT,
        position_size_pct: float = 1.0,
    ) -> None:
        self._initial_capital = initial_capital
        self._fee_pct = fee_pct
        self._slippage_pct = slippage_pct
        self._position_size_pct = position_size_pct

    def run(
        self,
        df: pd.DataFrame,
        signal_fn: Callable[[pd.DataFrame, int], Optional[dict[str, Any]]],
    ) -> BacktestResult:
        """Execute backtest.

        Parameters
        ----------
        df : pd.DataFrame
            OHLCV data with at least: timestamp/index, open, high, low, close, volume.
        signal_fn : Callable
            Function(df, current_index) -> dict with keys:
                "action": "long" | "short" | "close" | None
                "stop_loss": float (optional)
                "take_profit": float (optional)

        Returns
        -------
        BacktestResult with trades, equity curve, and 20 metrics.
        """
        capital = self._initial_capital
        trades: list[Trade] = []
        equity: list[float] = [capital]
        timestamps: list[datetime] = []

        # Position state
        in_position = False
        position_side: str = ""
        entry_price: float = 0.0
        entry_time: Optional[datetime] = None
        position_size: float = 0.0
        stop_loss: Optional[float] = None
        take_profit: Optional[float] = None

        for i in range(1, len(df)):
            row = df.iloc[i]
            ts = row.get("timestamp", df.index[i] if isinstance(df.index, pd.DatetimeIndex) else i)
            close = float(row["close"])
            high = float(row["high"])
            low = float(row["low"])

            if in_position:
                # Check stop loss / take profit
                exit_reason = ""
                exit_price = 0.0
                triggered = False

                if position_side == "long":
                    if stop_loss is not None and low <= stop_loss:
                        exit_price = stop_loss
                        exit_reason = "sl"
                        triggered = True
                    elif take_profit is not None and high >= take_profit:
                        exit_price = take_profit
                        exit_reason = "tp"
                        triggered = True
                elif position_side == "short":
                    if stop_loss is not None and high >= stop_loss:
                        exit_price = stop_loss
                        exit_reason = "sl"
                        triggered = True
                    elif take_profit is not None and low <= take_profit:
                        exit_price = take_profit
                        exit_reason = "tp"
                        triggered = True

                if triggered:
                    trade = self._close_position(
                        entry_time, ts, position_side, entry_price,
                        exit_price, position_size, exit_reason,
                    )
                    trades.append(trade)
                    capital += trade.pnl
                    in_position = False

            # Check for new signal
            if not in_position:
                signal = signal_fn(df, i)
                if signal and signal.get("action") in ("long", "short"):
                    position_side = signal["action"]
                    # Apply slippage to entry
                    if position_side == "long":
                        entry_price = close * (1 + self._slippage_pct)
                    else:
                        entry_price = close * (1 - self._slippage_pct)

                    position_size = (capital * self._position_size_pct) / entry_price
                    entry_time = ts
                    stop_loss = signal.get("stop_loss")
                    take_profit = signal.get("take_profit")
                    in_position = True

            elif in_position:
                signal = signal_fn(df, i)
                if signal and signal.get("action") == "close":
                    if position_side == "long":
                        exit_price = close * (1 - self._slippage_pct)
                    else:
                        exit_price = close * (1 + self._slippage_pct)
                    trade = self._close_position(
                        entry_time, ts, position_side, entry_price,
                        exit_price, position_size, "signal",
                    )
                    trades.append(trade)
                    capital += trade.pnl
                    in_position = False

            equity.append(capital)
            if isinstance(ts, (datetime, pd.Timestamp)):
                timestamps.append(ts)

        # Force close any remaining position
        if in_position:
            last_close = float(df.iloc[-1]["close"])
            last_ts = df.iloc[-1].get(
                "timestamp",
                df.index[-1] if isinstance(df.index, pd.DatetimeIndex) else len(df) - 1,
            )
            if position_side == "long":
                exit_price = last_close * (1 - self._slippage_pct)
            else:
                exit_price = last_close * (1 + self._slippage_pct)
            trade = self._close_position(
                entry_time, last_ts, position_side, entry_price,
                exit_price, position_size, "forced",
            )
            trades.append(trade)
            capital += trade.pnl

        equity_series = pd.Series(equity)
        total_return_pct = (capital - self._initial_capital) / self._initial_capital * 100

        # Compute performance metrics
        from engine.backtest.performance_analyzer import PerformanceAnalyzer
        analyzer = PerformanceAnalyzer()
        metrics = analyzer.calculate_all(trades, equity_series, self._initial_capital)

        start_date = df.iloc[0].get("timestamp", datetime.min)
        end_date = df.iloc[-1].get("timestamp", datetime.max)

        return BacktestResult(
            trades=trades,
            equity_curve=equity_series,
            initial_capital=self._initial_capital,
            final_capital=capital,
            total_return_pct=total_return_pct,
            n_trades=len(trades),
            start_date=start_date,
            end_date=end_date,
            metrics=metrics,
        )

    def _close_position(
        self,
        entry_time: Any,
        exit_time: Any,
        side: str,
        entry_price: float,
        exit_price: float,
        size: float,
        reason: str,
    ) -> Trade:
        """Calculate PnL and create Trade record."""
        if side == "long":
            raw_pnl = (exit_price - entry_price) * size
        else:
            raw_pnl = (entry_price - exit_price) * size

        notional = entry_price * size
        fees = notional * self._fee_pct * 2  # entry + exit
        slippage_cost = notional * self._slippage_pct * 2
        pnl = raw_pnl - fees

        pnl_pct = pnl / notional * 100 if notional > 0 else 0.0

        return Trade(
            entry_time=entry_time,
            exit_time=exit_time,
            side=side,
            entry_price=entry_price,
            exit_price=exit_price,
            size=size,
            pnl=pnl,
            pnl_pct=pnl_pct,
            fees=fees,
            slippage_cost=slippage_cost,
            reason=reason,
        )
