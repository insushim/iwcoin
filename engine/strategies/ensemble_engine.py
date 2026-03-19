"""Ensemble engine — collects signals from all active strategies and produces
a weighted vote to decide whether to act."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from loguru import logger

from engine.strategies.base_strategy import BaseStrategy, Signal
from engine.utils.constants import Regime, Side


# ── Regime-based weight tables ───────────────────────────────────────────────

REGIME_WEIGHTS: dict[str, dict[str, float]] = {
    "BULL": {
        "trend_following": 0.35,
        "momentum_breakout": 0.25,
        "mean_reversion_bb": 0.10,
        "grid_trading": 0.10,
        "smart_dca": 0.20,
    },
    "SIDEWAYS": {
        "trend_following": 0.10,
        "momentum_breakout": 0.10,
        "mean_reversion_bb": 0.30,
        "grid_trading": 0.30,
        "smart_dca": 0.20,
    },
    "BEAR": {
        "trend_following": 0.20,
        "momentum_breakout": 0.15,
        "mean_reversion_bb": 0.25,
        "grid_trading": 0.15,
        "smart_dca": 0.25,
    },
}

VOTE_THRESHOLD = 0.6
STRONG_AGREEMENT_MIN = 3  # strategies that must agree for "strong signal"
STRONG_SIGNAL_SIZE_MULT = 1.5


@dataclass
class EnsembleVote:
    symbol: str
    side: Optional[Side]
    weighted_score: float
    agreeing_strategies: list[str]
    is_strong: bool
    size_multiplier: float
    vetoed: bool = False
    veto_reason: str = ""
    raw_signals: list[Signal] = field(default_factory=list)


class EnsembleEngine:
    """Collects signals from all active strategies and applies weighted voting.

    Features:
    - Regime-dependent weighting
    - ML veto (pluggable)
    - Fear & Greed override (>85 → no buy, <15 → no sell)
    - 3+ strategy agreement → strong signal (1.5× size)
    """

    def __init__(
        self,
        strategies: dict[str, BaseStrategy],
        regime_detector: Any = None,
        ml_model: Any = None,
        fear_greed_fetcher: Any = None,
    ) -> None:
        self.strategies = strategies
        self.regime_detector = regime_detector
        self.ml_model = ml_model
        self.fear_greed_fetcher = fear_greed_fetcher

    async def vote(self, symbol: str) -> EnsembleVote:
        """Run all strategies and produce a weighted vote."""
        # 1. Collect signals
        signals: list[Signal] = []
        for name, strat in self.strategies.items():
            try:
                sig = await strat.generate_signal(symbol)
                if sig is not None:
                    signals.append(sig)
            except Exception:
                logger.exception("[Ensemble] Error from strategy {}", name)

        if not signals:
            return EnsembleVote(
                symbol=symbol,
                side=None,
                weighted_score=0.0,
                agreeing_strategies=[],
                is_strong=False,
                size_multiplier=1.0,
                raw_signals=[],
            )

        # 2. Determine current regime
        regime = await self._get_regime(symbol)
        weights = self._get_weights(regime)

        # 3. Weighted vote per side
        long_score = 0.0
        short_score = 0.0
        long_strats: list[str] = []
        short_strats: list[str] = []

        for sig in signals:
            w = weights.get(sig.strategy_name, 0.1)
            weighted = sig.confidence * w
            if sig.side in (Side.LONG, Side.BUY):
                long_score += weighted
                long_strats.append(sig.strategy_name)
            elif sig.side in (Side.SHORT, Side.SELL):
                short_score += weighted
                short_strats.append(sig.strategy_name)

        # Dominant direction
        if long_score >= short_score:
            dominant_side = Side.LONG
            dominant_score = long_score
            agreeing = long_strats
        else:
            dominant_side = Side.SHORT
            dominant_score = short_score
            agreeing = short_strats

        # Normalise score (sum of weights can exceed 1)
        total_weight = sum(weights.values()) or 1.0
        normalised_score = dominant_score / total_weight

        is_strong = len(agreeing) >= STRONG_AGREEMENT_MIN
        size_mult = STRONG_SIGNAL_SIZE_MULT if is_strong else 1.0

        result = EnsembleVote(
            symbol=symbol,
            side=dominant_side if normalised_score >= VOTE_THRESHOLD else None,
            weighted_score=round(normalised_score, 4),
            agreeing_strategies=agreeing,
            is_strong=is_strong,
            size_multiplier=size_mult,
            raw_signals=signals,
        )

        # 4. ML veto
        if result.side is not None and self.ml_model is not None:
            result = await self._ml_veto(result)

        # 5. Fear & Greed override
        if result.side is not None:
            result = await self._fear_greed_override(result)

        logger.info(
            "[Ensemble] {} vote: side={} score={:.3f} agree={} strong={} veto={}",
            symbol,
            result.side,
            result.weighted_score,
            result.agreeing_strategies,
            result.is_strong,
            result.vetoed,
        )
        return result

    # ── Regime ───────────────────────────────────────────────────────────

    async def _get_regime(self, symbol: str) -> str:
        if self.regime_detector is None:
            return "SIDEWAYS"
        try:
            regime = await self.regime_detector.detect(symbol)
            if isinstance(regime, Regime):
                if regime in (Regime.TRENDING_UP,):
                    return "BULL"
                if regime in (Regime.TRENDING_DOWN,):
                    return "BEAR"
            if isinstance(regime, str):
                regime_upper = regime.upper()
                if regime_upper in REGIME_WEIGHTS:
                    return regime_upper
            return "SIDEWAYS"
        except Exception:
            logger.warning("[Ensemble] Regime detection failed, using SIDEWAYS")
            return "SIDEWAYS"

    @staticmethod
    def _get_weights(regime: str) -> dict[str, float]:
        return REGIME_WEIGHTS.get(regime, REGIME_WEIGHTS["SIDEWAYS"])

    # ── ML veto ──────────────────────────────────────────────────────────

    async def _ml_veto(self, vote: EnsembleVote) -> EnsembleVote:
        try:
            prediction = await self.ml_model.predict(vote.symbol, vote.side)
            if prediction is not None and prediction.get("veto", False):
                vote.vetoed = True
                vote.veto_reason = prediction.get("reason", "ML model vetoed")
                vote.side = None
                logger.info("[Ensemble] ML veto: {}", vote.veto_reason)
        except Exception:
            logger.warning("[Ensemble] ML veto check failed, proceeding")
        return vote

    # ── Fear & Greed ─────────────────────────────────────────────────────

    async def _fear_greed_override(self, vote: EnsembleVote) -> EnsembleVote:
        if self.fear_greed_fetcher is None:
            return vote
        try:
            fg = await self.fear_greed_fetcher.get()
            if fg is None:
                return vote

            value = fg if isinstance(fg, (int, float)) else fg.get("value", 50)

            if value > 85 and vote.side in (Side.LONG, Side.BUY):
                vote.vetoed = True
                vote.veto_reason = f"Fear&Greed={value} >85 — no buy in extreme greed"
                vote.side = None
                logger.info("[Ensemble] F&G override: {}", vote.veto_reason)

            elif value < 15 and vote.side in (Side.SHORT, Side.SELL):
                vote.vetoed = True
                vote.veto_reason = f"Fear&Greed={value} <15 — no sell in extreme fear"
                vote.side = None
                logger.info("[Ensemble] F&G override: {}", vote.veto_reason)

        except Exception:
            logger.warning("[Ensemble] Fear&Greed fetch failed, proceeding")
        return vote
