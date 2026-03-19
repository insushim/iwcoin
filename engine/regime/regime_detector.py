"""Market regime detection using multi-timeframe analysis."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

import numpy as np
from loguru import logger

from engine.regime.fear_greed_fetcher import FearGreedFetcher


class Regime(str, Enum):
    BULL = "BULL"
    BEAR = "BEAR"
    SIDEWAYS = "SIDEWAYS"
    UNCERTAIN = "UNCERTAIN"


# Timeframe weights for voting
_TF_WEIGHTS = {"1d": 0.50, "4h": 0.30, "1h": 0.20}


class RegimeDetector:
    """Detects market regime via multi-timeframe technical analysis + Fear & Greed."""

    def __init__(self, exchange_manager: Any, config: Any) -> None:
        self._exchange = exchange_manager
        self._config = config
        self._fng = FearGreedFetcher()
        self._history: list[dict] = []

    # ── Public API ──────────────────────────────────────────

    async def detect_regime(self, symbol: str = "BTC/USDT") -> dict:
        """Detect current market regime across 3 timeframes with F&G overlay."""
        fng_task = asyncio.create_task(self._fng.fetch_current())
        tf_tasks = {
            tf: asyncio.create_task(self._analyse_timeframe(symbol, tf))
            for tf in _TF_WEIGHTS
        }

        fng_value = await fng_task
        tf_results: dict[str, dict] = {}
        for tf, task in tf_tasks.items():
            try:
                tf_results[tf] = await task
            except Exception as e:
                logger.warning("Timeframe {} analysis failed: {}", tf, e)
                tf_results[tf] = {"regime": Regime.UNCERTAIN, "confidence": 0.0, "details": {}}

        # Weighted vote
        regime, confidence, details = self._weighted_vote(tf_results, fng_value)
        adx = tf_results.get("1d", {}).get("details", {}).get("adx", 0.0)

        result = {
            "regime": regime.value,
            "confidence": round(confidence, 3),
            "fear_greed": fng_value,
            "fear_greed_zone": self._fng.get_zone(fng_value),
            "adx": round(adx, 2),
            "details": details,
            "recommended_strategies": self._recommend_strategies(regime),
            "risk_level": self._risk_level(regime, fng_value),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        self._history.append(result)
        if len(self._history) > 1000:
            self._history = self._history[-500:]

        logger.info(
            "Regime: {} (conf={:.1%}) | F&G={} ({}) | ADX={:.1f}",
            regime.value, confidence, fng_value,
            self._fng.get_zone(fng_value), adx,
        )
        return result

    async def get_regime_history(self, days: int = 30) -> list[dict]:
        """Return stored regime detection history (in-memory, up to `days` most recent)."""
        # Each detect call is ~1 entry; return last N*24 entries (approx hourly)
        limit = days * 24
        return self._history[-limit:]

    # ── Timeframe Analysis ──────────────────────────────────

    async def _analyse_timeframe(self, symbol: str, timeframe: str) -> dict:
        """Run technical analysis on a single timeframe and return regime vote."""
        limit = 250
        ohlcv = await self._exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        if not ohlcv or len(ohlcv) < 50:
            return {"regime": Regime.UNCERTAIN, "confidence": 0.0, "details": {}}

        closes = np.array([c[4] for c in ohlcv], dtype=np.float64)
        highs = np.array([c[2] for c in ohlcv], dtype=np.float64)
        lows = np.array([c[3] for c in ohlcv], dtype=np.float64)

        # Indicators
        adx, di_plus, di_minus = self._calc_adx(highs, lows, closes, period=14)
        sma200 = self._sma(closes, 200) if len(closes) >= 200 else self._sma(closes, len(closes))
        macd_line, signal_line = self._calc_macd(closes)
        bb_width = self._calc_bb_width(closes, period=20)

        current_close = closes[-1]
        details = {
            "adx": adx,
            "di_plus": di_plus,
            "di_minus": di_minus,
            "sma200": sma200,
            "price_vs_sma200": (current_close / sma200 - 1) * 100 if sma200 > 0 else 0.0,
            "macd": macd_line,
            "macd_signal": signal_line,
            "bb_width": bb_width,
        }

        # Score: positive = bullish, negative = bearish
        score = 0.0
        conf_factors = 0.0

        # ADX trend strength
        if adx > 25:
            if di_plus > di_minus:
                score += 2.0
            else:
                score -= 2.0
            conf_factors += 2.0
        else:
            conf_factors += 0.5  # weak trend

        # SMA200
        if sma200 > 0:
            pct = (current_close / sma200 - 1) * 100
            if pct > 5:
                score += 1.5
            elif pct > 0:
                score += 0.5
            elif pct > -5:
                score -= 0.5
            else:
                score -= 1.5
            conf_factors += 1.5

        # MACD
        if macd_line > signal_line:
            score += 1.0
        else:
            score -= 1.0
        conf_factors += 1.0

        # Bollinger Width (low = sideways squeeze)
        if bb_width < 0.03:
            score *= 0.5  # dampen toward sideways
        conf_factors += 0.5

        # Determine regime
        max_score = conf_factors if conf_factors > 0 else 1.0
        normalized = score / max_score  # -1 to +1 range approx

        if adx < 20 or abs(normalized) < 0.2:
            regime = Regime.SIDEWAYS
            confidence = 0.5 + (20 - min(adx, 20)) / 40
        elif normalized > 0.2:
            regime = Regime.BULL
            confidence = min(0.5 + normalized * 0.5, 1.0)
        elif normalized < -0.2:
            regime = Regime.BEAR
            confidence = min(0.5 + abs(normalized) * 0.5, 1.0)
        else:
            regime = Regime.UNCERTAIN
            confidence = 0.3

        return {"regime": regime, "confidence": confidence, "details": details}

    # ── Weighted Vote ───────────────────────────────────────

    def _weighted_vote(
        self,
        tf_results: dict[str, dict],
        fng_value: int,
    ) -> tuple[Regime, float, dict]:
        """Combine timeframe votes with F&G adjustment."""
        regime_scores: dict[Regime, float] = {r: 0.0 for r in Regime}
        total_confidence = 0.0
        all_details: dict[str, dict] = {}

        for tf, weight in _TF_WEIGHTS.items():
            res = tf_results.get(tf, {})
            regime = res.get("regime", Regime.UNCERTAIN)
            conf = res.get("confidence", 0.0)
            regime_scores[regime] += weight * conf
            total_confidence += weight * conf
            all_details[tf] = res.get("details", {})

        # F&G adjustment: extreme fear boosts BEAR score, extreme greed boosts BULL
        if fng_value <= 20:
            regime_scores[Regime.BEAR] += 0.15
            regime_scores[Regime.BULL] -= 0.10
        elif fng_value <= 35:
            regime_scores[Regime.BEAR] += 0.05
        elif fng_value >= 80:
            regime_scores[Regime.BULL] += 0.15
            regime_scores[Regime.BEAR] -= 0.10
        elif fng_value >= 65:
            regime_scores[Regime.BULL] += 0.05

        best_regime = max(regime_scores, key=regime_scores.get)  # type: ignore[arg-type]
        best_score = regime_scores[best_regime]
        confidence = min(best_score / max(total_confidence, 0.01), 1.0)

        return best_regime, confidence, all_details

    # ── Strategy Recommendations ────────────────────────────

    @staticmethod
    def _recommend_strategies(regime: Regime) -> list[str]:
        mapping = {
            Regime.BULL: ["trend_following", "momentum", "rebalancer", "funding_arb"],
            Regime.BEAR: ["dca", "funding_arb", "mean_reversion"],
            Regime.SIDEWAYS: ["grid", "mean_reversion", "funding_arb", "dca"],
            Regime.UNCERTAIN: ["dca"],
        }
        return mapping.get(regime, ["dca"])

    @staticmethod
    def _risk_level(regime: Regime, fng_value: int) -> str:
        if regime == Regime.BEAR or fng_value <= 15:
            return "high"
        if regime == Regime.UNCERTAIN or fng_value <= 30 or fng_value >= 85:
            return "medium"
        return "low"

    # ── Indicator Calculations ──────────────────────────────

    @staticmethod
    def _sma(data: np.ndarray, period: int) -> float:
        if len(data) < period:
            return float(np.mean(data))
        return float(np.mean(data[-period:]))

    @staticmethod
    def _calc_adx(
        highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14
    ) -> tuple[float, float, float]:
        """Calculate ADX, DI+, DI- using Wilder's smoothing."""
        n = len(closes)
        if n < period + 1:
            return 0.0, 0.0, 0.0

        tr = np.zeros(n)
        dm_plus = np.zeros(n)
        dm_minus = np.zeros(n)

        for i in range(1, n):
            h_l = highs[i] - lows[i]
            h_cp = abs(highs[i] - closes[i - 1])
            l_cp = abs(lows[i] - closes[i - 1])
            tr[i] = max(h_l, h_cp, l_cp)

            up = highs[i] - highs[i - 1]
            down = lows[i - 1] - lows[i]
            dm_plus[i] = up if (up > down and up > 0) else 0.0
            dm_minus[i] = down if (down > up and down > 0) else 0.0

        # Wilder's smoothing
        atr = np.zeros(n)
        adm_plus = np.zeros(n)
        adm_minus = np.zeros(n)

        atr[period] = np.sum(tr[1 : period + 1])
        adm_plus[period] = np.sum(dm_plus[1 : period + 1])
        adm_minus[period] = np.sum(dm_minus[1 : period + 1])

        for i in range(period + 1, n):
            atr[i] = atr[i - 1] - atr[i - 1] / period + tr[i]
            adm_plus[i] = adm_plus[i - 1] - adm_plus[i - 1] / period + dm_plus[i]
            adm_minus[i] = adm_minus[i - 1] - adm_minus[i - 1] / period + dm_minus[i]

        if atr[-1] == 0:
            return 0.0, 0.0, 0.0

        di_p = 100 * adm_plus[-1] / atr[-1]
        di_m = 100 * adm_minus[-1] / atr[-1]
        dx_sum = di_p + di_m
        if dx_sum == 0:
            return 0.0, di_p, di_m

        # Calculate DX series and smooth to get ADX
        dx_vals = []
        for i in range(period, n):
            if atr[i] == 0:
                continue
            dp = 100 * adm_plus[i] / atr[i]
            dm = 100 * adm_minus[i] / atr[i]
            s = dp + dm
            if s > 0:
                dx_vals.append(abs(dp - dm) / s * 100)

        if len(dx_vals) < period:
            adx = float(np.mean(dx_vals)) if dx_vals else 0.0
        else:
            # Wilder smooth DX
            adx = float(np.mean(dx_vals[:period]))
            for dx in dx_vals[period:]:
                adx = (adx * (period - 1) + dx) / period

        return adx, di_p, di_m

    @staticmethod
    def _calc_macd(
        closes: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9
    ) -> tuple[float, float]:
        """Return (macd_line, signal_line) using EMA."""
        if len(closes) < slow + signal:
            return 0.0, 0.0

        def ema(data: np.ndarray, period: int) -> np.ndarray:
            result = np.zeros(len(data))
            k = 2.0 / (period + 1)
            result[0] = data[0]
            for i in range(1, len(data)):
                result[i] = data[i] * k + result[i - 1] * (1 - k)
            return result

        ema_fast = ema(closes, fast)
        ema_slow = ema(closes, slow)
        macd_line = ema_fast - ema_slow
        sig = ema(macd_line, signal)
        return float(macd_line[-1]), float(sig[-1])

    @staticmethod
    def _calc_bb_width(closes: np.ndarray, period: int = 20, std_mult: float = 2.0) -> float:
        """Return Bollinger Band width as fraction of middle band."""
        if len(closes) < period:
            return 0.0
        window = closes[-period:]
        mid = float(np.mean(window))
        if mid == 0:
            return 0.0
        std = float(np.std(window))
        upper = mid + std_mult * std
        lower = mid - std_mult * std
        return (upper - lower) / mid
