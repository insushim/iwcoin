"""Performance metrics calculator for backtests and live trading."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
from loguru import logger

if TYPE_CHECKING:
    from engine.backtest.backtester import Trade


class PerformanceAnalyzer:
    """Calculate 20 performance metrics from trades and equity curve."""

    ANNUAL_BARS_1H = 365.25 * 24  # for hourly data
    RISK_FREE_RATE = 0.0  # crypto: 0%

    def calculate_all(
        self,
        trades: list[Trade],
        equity_curve: pd.Series,
        initial_capital: float,
        bars_per_year: float = ANNUAL_BARS_1H,
    ) -> dict[str, float]:
        """Compute all metrics.

        Returns dict with 20 named metrics.
        """
        if not trades:
            return self._empty_metrics()

        pnls = np.array([t.pnl for t in trades])
        pnl_pcts = np.array([t.pnl_pct for t in trades])
        wins = pnls[pnls > 0]
        losses = pnls[pnls < 0]

        final_capital = float(equity_curve.iloc[-1])
        total_return = (final_capital - initial_capital) / initial_capital
        n_bars = len(equity_curve)
        years = n_bars / bars_per_year if bars_per_year > 0 else 1.0

        # CAGR
        cagr = (final_capital / initial_capital) ** (1 / max(years, 1e-10)) - 1 if final_capital > 0 else -1.0

        # Max drawdown
        peak = equity_curve.expanding().max()
        dd = (equity_curve - peak) / peak
        mdd = float(dd.min()) * 100  # as negative percentage

        # Returns per bar for Sharpe/Sortino
        returns = equity_curve.pct_change().dropna()
        mean_ret = float(returns.mean())
        std_ret = float(returns.std()) if len(returns) > 1 else 1e-10

        # Sharpe
        sharpe = (mean_ret - self.RISK_FREE_RATE / bars_per_year) / max(std_ret, 1e-10) * np.sqrt(bars_per_year)

        # Sortino (downside deviation)
        downside = returns[returns < 0]
        downside_std = float(downside.std()) if len(downside) > 1 else 1e-10
        sortino = (mean_ret - self.RISK_FREE_RATE / bars_per_year) / max(downside_std, 1e-10) * np.sqrt(bars_per_year)

        # Calmar
        calmar = cagr / max(abs(mdd / 100), 1e-10)

        # Win rate
        win_rate = len(wins) / len(pnls) * 100 if len(pnls) > 0 else 0.0

        # Profit factor
        gross_profit = float(wins.sum()) if len(wins) > 0 else 0.0
        gross_loss = float(abs(losses.sum())) if len(losses) > 0 else 1e-10
        profit_factor = gross_profit / max(gross_loss, 1e-10)

        # Average win / loss
        avg_win = float(wins.mean()) if len(wins) > 0 else 0.0
        avg_loss = float(losses.mean()) if len(losses) > 0 else 0.0
        avg_win_pct = float(pnl_pcts[pnls > 0].mean()) if len(wins) > 0 else 0.0
        avg_loss_pct = float(pnl_pcts[pnls < 0].mean()) if len(losses) > 0 else 0.0

        # Max consecutive wins/losses
        max_consec_wins = self._max_consecutive(pnls, positive=True)
        max_consec_losses = self._max_consecutive(pnls, positive=False)

        # Expectancy
        expectancy = float(pnls.mean())

        # Payoff ratio
        payoff_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else float("inf")

        # Total fees
        total_fees = sum(t.fees for t in trades)

        # Monthly breakdown
        monthly = self._monthly_breakdown(trades)

        metrics = {
            "total_return_pct": round(total_return * 100, 2),
            "cagr_pct": round(cagr * 100, 2),
            "max_drawdown_pct": round(mdd, 2),
            "sharpe_ratio": round(sharpe, 3),
            "sortino_ratio": round(sortino, 3),
            "calmar_ratio": round(calmar, 3),
            "win_rate_pct": round(win_rate, 2),
            "profit_factor": round(profit_factor, 3),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "avg_win_pct": round(avg_win_pct, 2),
            "avg_loss_pct": round(avg_loss_pct, 2),
            "max_consecutive_wins": max_consec_wins,
            "max_consecutive_losses": max_consec_losses,
            "expectancy": round(expectancy, 2),
            "payoff_ratio": round(payoff_ratio, 3),
            "n_trades": len(trades),
            "total_fees": round(total_fees, 2),
            "n_winning_months": sum(1 for v in monthly.values() if v > 0),
            "n_losing_months": sum(1 for v in monthly.values() if v < 0),
        }
        return metrics

    def _max_consecutive(self, pnls: np.ndarray, positive: bool) -> int:
        max_count = 0
        count = 0
        for p in pnls:
            if (positive and p > 0) or (not positive and p <= 0):
                count += 1
                max_count = max(max_count, count)
            else:
                count = 0
        return max_count

    def _monthly_breakdown(self, trades: list[Trade]) -> dict[str, float]:
        """Aggregate PnL by month."""
        monthly: dict[str, float] = {}
        for t in trades:
            try:
                key = pd.Timestamp(t.exit_time).strftime("%Y-%m")
            except Exception:
                continue
            monthly[key] = monthly.get(key, 0.0) + t.pnl
        return monthly

    def _empty_metrics(self) -> dict[str, float]:
        return {
            "total_return_pct": 0.0,
            "cagr_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "sharpe_ratio": 0.0,
            "sortino_ratio": 0.0,
            "calmar_ratio": 0.0,
            "win_rate_pct": 0.0,
            "profit_factor": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "avg_win_pct": 0.0,
            "avg_loss_pct": 0.0,
            "max_consecutive_wins": 0,
            "max_consecutive_losses": 0,
            "expectancy": 0.0,
            "payoff_ratio": 0.0,
            "n_trades": 0,
            "total_fees": 0.0,
            "n_winning_months": 0,
            "n_losing_months": 0,
        }

    def print_report(self, metrics: dict[str, float]) -> str:
        """Format metrics as human-readable report string."""
        lines = [
            "=" * 50,
            "       PERFORMANCE REPORT",
            "=" * 50,
            f"  Total Return:       {metrics['total_return_pct']:>10.2f}%",
            f"  CAGR:               {metrics['cagr_pct']:>10.2f}%",
            f"  Max Drawdown:       {metrics['max_drawdown_pct']:>10.2f}%",
            f"  Sharpe Ratio:       {metrics['sharpe_ratio']:>10.3f}",
            f"  Sortino Ratio:      {metrics['sortino_ratio']:>10.3f}",
            f"  Calmar Ratio:       {metrics['calmar_ratio']:>10.3f}",
            "-" * 50,
            f"  Win Rate:           {metrics['win_rate_pct']:>10.2f}%",
            f"  Profit Factor:      {metrics['profit_factor']:>10.3f}",
            f"  Payoff Ratio:       {metrics['payoff_ratio']:>10.3f}",
            f"  Expectancy:         {metrics['expectancy']:>10.2f}",
            "-" * 50,
            f"  Avg Win:            {metrics['avg_win']:>10.2f} ({metrics['avg_win_pct']:.2f}%)",
            f"  Avg Loss:           {metrics['avg_loss']:>10.2f} ({metrics['avg_loss_pct']:.2f}%)",
            f"  Max Consec Wins:    {metrics['max_consecutive_wins']:>10}",
            f"  Max Consec Losses:  {metrics['max_consecutive_losses']:>10}",
            "-" * 50,
            f"  Total Trades:       {metrics['n_trades']:>10}",
            f"  Total Fees:         {metrics['total_fees']:>10.2f}",
            f"  Winning Months:     {metrics['n_winning_months']:>10}",
            f"  Losing Months:      {metrics['n_losing_months']:>10}",
            "=" * 50,
        ]
        return "\n".join(lines)
