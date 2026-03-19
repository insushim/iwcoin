"""Rank strategies by composite score."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from loguru import logger


@dataclass
class RankedStrategy:
    """Strategy with its composite ranking score."""

    name: str
    sharpe: float
    profit_factor: float
    max_drawdown_pct: float  # negative number, e.g. -15.5
    composite_score: float
    rank: int = 0
    metrics: dict[str, Any] | None = None


class StrategyRanker:
    """Rank strategies by: Sharpe * 0.4 + PF * 0.3 + (1 - MDD/100) * 0.3.

    MDD is expected as a negative percentage (e.g. -15.5 for 15.5% drawdown).
    The formula uses abs(MDD).
    """

    W_SHARPE = 0.4
    W_PF = 0.3
    W_MDD = 0.3

    def __init__(
        self,
        w_sharpe: float = W_SHARPE,
        w_pf: float = W_PF,
        w_mdd: float = W_MDD,
    ) -> None:
        self._w_sharpe = w_sharpe
        self._w_pf = w_pf
        self._w_mdd = w_mdd

    def score(self, sharpe: float, profit_factor: float, max_drawdown_pct: float) -> float:
        """Compute composite score for a single strategy."""
        mdd_abs = abs(max_drawdown_pct)
        mdd_component = 1.0 - mdd_abs / 100.0
        mdd_component = max(mdd_component, 0.0)  # clamp to 0 if MDD > 100%

        return (
            self._w_sharpe * sharpe
            + self._w_pf * profit_factor
            + self._w_mdd * mdd_component
        )

    def rank(
        self,
        strategies: list[dict[str, Any]],
    ) -> list[RankedStrategy]:
        """Rank a list of strategy results.

        Parameters
        ----------
        strategies : list[dict]
            Each dict must have: "name", "sharpe_ratio", "profit_factor", "max_drawdown_pct".
            May include additional metrics.

        Returns
        -------
        list[RankedStrategy] sorted by composite score descending.
        """
        ranked: list[RankedStrategy] = []

        for s in strategies:
            name = s.get("name", "unnamed")
            sharpe = float(s.get("sharpe_ratio", 0.0))
            pf = float(s.get("profit_factor", 0.0))
            mdd = float(s.get("max_drawdown_pct", 0.0))

            composite = self.score(sharpe, pf, mdd)
            ranked.append(RankedStrategy(
                name=name,
                sharpe=sharpe,
                profit_factor=pf,
                max_drawdown_pct=mdd,
                composite_score=round(composite, 4),
                metrics=s,
            ))

        ranked.sort(key=lambda x: x.composite_score, reverse=True)
        for i, r in enumerate(ranked):
            r.rank = i + 1

        if ranked:
            logger.info(
                "Strategy ranking: #1 {} (score={:.4f}), #last {} (score={:.4f})",
                ranked[0].name, ranked[0].composite_score,
                ranked[-1].name, ranked[-1].composite_score,
            )

        return ranked

    def print_ranking(self, ranked: list[RankedStrategy]) -> str:
        """Format ranking as table string."""
        lines = [
            f"{'Rank':<6}{'Strategy':<25}{'Sharpe':<10}{'PF':<10}{'MDD%':<10}{'Score':<10}",
            "-" * 71,
        ]
        for r in ranked:
            lines.append(
                f"{r.rank:<6}{r.name:<25}{r.sharpe:<10.3f}{r.profit_factor:<10.3f}"
                f"{r.max_drawdown_pct:<10.2f}{r.composite_score:<10.4f}"
            )
        return "\n".join(lines)
