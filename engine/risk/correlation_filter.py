"""Correlation filter – blocks highly correlated simultaneous positions."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

import numpy as np
from loguru import logger


@dataclass
class CorrelationConfig:
    lookback_days: int = 30
    pair_threshold: float = 0.8       # block same-direction if corr > this
    portfolio_threshold: float = 0.6  # weighted portfolio correlation cap
    cache_ttl_sec: int = 3600         # recalculate hourly


@dataclass
class _CacheEntry:
    correlation: float
    computed_at: float


class CorrelationFilter:
    """Calculate Pearson correlation between coin pairs and enforce limits."""

    def __init__(self, config: Optional[CorrelationConfig] = None) -> None:
        self.config = config or CorrelationConfig()
        # price_data[symbol] = list of daily close prices (most recent last)
        self._price_data: dict[str, list[float]] = {}
        # cache: (sym_a, sym_b) -> _CacheEntry   (sorted pair key)
        self._cache: dict[tuple[str, str], _CacheEntry] = {}

        logger.info(
            "CorrelationFilter initialised | pair_threshold={} portfolio_threshold={}",
            self.config.pair_threshold,
            self.config.portfolio_threshold,
        )

    # ── data ingestion ──────────────────────────────────────

    def update_prices(self, symbol: str, closes: list[float]) -> None:
        """Set or replace the daily close series for *symbol*."""
        self._price_data[symbol] = closes

    # ── pair-level check ────────────────────────────────────

    def pair_correlation(self, sym_a: str, sym_b: str) -> float:
        """Return Pearson correlation between two symbols (cached)."""
        key = tuple(sorted((sym_a, sym_b)))  # type: ignore[arg-type]
        now = time.time()
        cached = self._cache.get(key)  # type: ignore[arg-type]
        if cached and (now - cached.computed_at) < self.config.cache_ttl_sec:
            return cached.correlation

        corr = self._compute_correlation(sym_a, sym_b)
        self._cache[key] = _CacheEntry(correlation=corr, computed_at=now)  # type: ignore[arg-type]
        return corr

    def check_pair_entry(
        self,
        new_symbol: str,
        new_direction: str,
        open_positions: list[dict],
    ) -> dict:
        """Check if *new_symbol* in *new_direction* conflicts with open positions.

        open_positions: list of {"symbol": str, "direction": "long"|"short", "weight": float}

        Returns {"approved": bool, "reason": str, "conflicts": list}
        """
        conflicts: list[dict] = []
        for pos in open_positions:
            if pos["symbol"] == new_symbol:
                continue
            corr = self.pair_correlation(new_symbol, pos["symbol"])
            same_dir = new_direction == pos["direction"]
            if corr > self.config.pair_threshold and same_dir:
                conflicts.append({
                    "symbol": pos["symbol"],
                    "correlation": round(corr, 4),
                    "direction": pos["direction"],
                })

        if conflicts:
            reason = (
                f"Blocked: {new_symbol} {new_direction} correlated >{self.config.pair_threshold} "
                f"with {[c['symbol'] for c in conflicts]}"
            )
            logger.warning(reason)
            return {"approved": False, "reason": reason, "conflicts": conflicts}

        return {"approved": True, "reason": "pair correlation OK", "conflicts": []}

    # ── portfolio-level check ───────────────────────────────

    def portfolio_correlation(self, open_positions: list[dict]) -> float:
        """Compute weight-adjusted average pairwise correlation of portfolio.

        open_positions: list of {"symbol": str, "weight": float}
        """
        symbols = [p["symbol"] for p in open_positions]
        weights = np.array([p["weight"] for p in open_positions])
        n = len(symbols)
        if n < 2:
            return 0.0

        total_weight = weights.sum()
        if total_weight <= 0:
            return 0.0
        norm_w = weights / total_weight

        weighted_corr = 0.0
        pair_count = 0
        for i in range(n):
            for j in range(i + 1, n):
                corr = self.pair_correlation(symbols[i], symbols[j])
                w = norm_w[i] * norm_w[j]
                weighted_corr += corr * w
                pair_count += 1

        # Normalise by sum of weight products
        weight_product_sum = sum(
            norm_w[i] * norm_w[j] for i in range(n) for j in range(i + 1, n)
        )
        if weight_product_sum <= 0:
            return 0.0
        return weighted_corr / weight_product_sum

    def check_portfolio(self, open_positions: list[dict]) -> dict:
        """Return whether portfolio-level correlation is acceptable."""
        port_corr = self.portfolio_correlation(open_positions)
        ok = port_corr < self.config.portfolio_threshold
        reason = (
            f"Portfolio corr={port_corr:.4f} "
            f"{'<' if ok else '>='} threshold={self.config.portfolio_threshold}"
        )
        if not ok:
            logger.warning("Portfolio correlation too high: {:.4f}", port_corr)
        return {"approved": ok, "reason": reason, "portfolio_correlation": round(port_corr, 4)}

    # ── internals ───────────────────────────────────────────

    def _compute_correlation(self, sym_a: str, sym_b: str) -> float:
        a = self._price_data.get(sym_a)
        b = self._price_data.get(sym_b)
        if not a or not b:
            logger.debug("Missing price data for {} or {}, returning 0.0", sym_a, sym_b)
            return 0.0

        length = min(len(a), len(b), self.config.lookback_days)
        if length < 5:
            return 0.0

        arr_a = np.array(a[-length:], dtype=np.float64)
        arr_b = np.array(b[-length:], dtype=np.float64)

        # Use log returns
        ret_a = np.diff(np.log(arr_a))
        ret_b = np.diff(np.log(arr_b))

        if len(ret_a) < 3:
            return 0.0

        corr_matrix = np.corrcoef(ret_a, ret_b)
        corr = float(corr_matrix[0, 1])
        if np.isnan(corr):
            return 0.0
        return corr
