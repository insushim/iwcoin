"""Funding-rate arbitrage strategy — delta-neutral spot + futures.

Rules:
  - Entry when annualised funding rate > 10%
  - Exit when funding turns negative for 3 consecutive readings
  - Max 20% of total capital allocated, 10% per coin
  - Auto-rebalance hedge when delta drifts > 2%
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from loguru import logger

from engine.config import TradingConfig
from engine.strategies.base_strategy import BaseStrategy, Signal
from engine.utils.constants import Side

ANNUALISED_ENTRY_THRESHOLD = 0.10  # 10%
NEGATIVE_EXIT_COUNT = 3
MAX_CAPITAL_PCT = 0.20
MAX_PER_COIN_PCT = 0.10
HEDGE_DRIFT_THRESHOLD = 0.02  # 2%
FUNDING_PERIODS_PER_YEAR = 3 * 365  # 8h funding × 3/day × 365


@dataclass
class ArbPosition:
    symbol: str
    spot_amount: float = 0.0
    futures_amount: float = 0.0
    entry_funding_rate: float = 0.0
    negative_count: int = 0
    active: bool = False
    total_funding_collected: float = 0.0


class FundingRateArb(BaseStrategy):
    name = "funding_rate_arb"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._cycle_interval = 300.0  # check every 5 min
        self._arb_positions: dict[str, ArbPosition] = {}

    async def generate_signal(self, symbol: str) -> Optional[Signal]:
        funding_rate = await self._get_funding_rate(symbol)
        if funding_rate is None:
            return None

        annualised = funding_rate * FUNDING_PERIODS_PER_YEAR
        pos = self._arb_positions.get(symbol)

        # ── Active position: manage ──────────────────────────────────
        if pos and pos.active:
            return await self._manage(pos, funding_rate, annualised)

        # ── No position: check entry ─────────────────────────────────
        if annualised < ANNUALISED_ENTRY_THRESHOLD:
            return None

        # Capital checks
        total_allocated = sum(
            p.spot_amount for p in self._arb_positions.values() if p.active
        )
        # We don't know exact equity here; signal carries metadata for executor
        pos = ArbPosition(
            symbol=symbol,
            entry_funding_rate=funding_rate,
            active=True,
        )
        self._arb_positions[symbol] = pos

        logger.info(
            "[FundingArb] Entry {} — funding={:.6f} annual={:.2%}",
            symbol, funding_rate, annualised,
        )

        return Signal(
            symbol=symbol,
            side=Side.BUY,
            confidence=0.75,
            strategy_name=self.name,
            reason=f"Funding arb entry: annual={annualised:.2%}",
            metadata={
                "arb_type": "funding_rate",
                "funding_rate": funding_rate,
                "annualised": annualised,
                "max_capital_pct": MAX_CAPITAL_PCT,
                "max_per_coin_pct": MAX_PER_COIN_PCT,
                "hedge": True,  # executor should open spot long + futures short
            },
        )

    # ── Position management ──────────────────────────────────────────────

    async def _manage(
        self, pos: ArbPosition, funding_rate: float, annualised: float
    ) -> Optional[Signal]:
        # Track negative funding
        if funding_rate < 0:
            pos.negative_count += 1
        else:
            pos.negative_count = 0
            pos.total_funding_collected += abs(funding_rate)

        # Exit if negative 3 consecutive times
        if pos.negative_count >= NEGATIVE_EXIT_COUNT:
            pos.active = False
            logger.info(
                "[FundingArb] Exit {} — {} consecutive negative fundings",
                pos.symbol, NEGATIVE_EXIT_COUNT,
            )
            return Signal(
                symbol=pos.symbol,
                side=Side.SELL,
                confidence=0.9,
                strategy_name=self.name,
                reason=f"Funding turned negative {NEGATIVE_EXIT_COUNT}x",
                metadata={
                    "arb_type": "funding_rate",
                    "close_hedge": True,
                    "total_funding_collected": pos.total_funding_collected,
                },
            )

        # Auto-rebalance hedge
        rebalance = await self._check_hedge_drift(pos)
        if rebalance is not None:
            return rebalance

        return None

    async def _check_hedge_drift(self, pos: ArbPosition) -> Optional[Signal]:
        """Rebalance if spot/futures delta drifts > threshold."""
        if pos.spot_amount == 0 and pos.futures_amount == 0:
            return None

        total = max(abs(pos.spot_amount), abs(pos.futures_amount), 1e-10)
        drift = abs(abs(pos.spot_amount) - abs(pos.futures_amount)) / total

        if drift <= HEDGE_DRIFT_THRESHOLD:
            return None

        logger.info("[FundingArb] Rebalancing {} — drift={:.2%}", pos.symbol, drift)

        return Signal(
            symbol=pos.symbol,
            side=Side.BUY,
            confidence=0.6,
            strategy_name=self.name,
            reason=f"Hedge rebalance drift={drift:.2%}",
            metadata={
                "arb_type": "funding_rate",
                "rebalance": True,
                "drift": drift,
            },
        )

    # ── Funding rate fetch ───────────────────────────────────────────────

    async def _get_funding_rate(self, symbol: str) -> Optional[float]:
        try:
            if hasattr(self.exchange, "fetch_funding_rate"):
                data = await self.exchange.fetch_funding_rate(symbol)
                if isinstance(data, dict):
                    return data.get("fundingRate")
                return data
            return None
        except Exception:
            logger.warning("[FundingArb] Failed to fetch funding rate for {}", symbol)
            return None
