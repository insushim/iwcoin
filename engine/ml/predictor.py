"""Real-time predictor using the trained ensemble model."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

import pandas as pd
from loguru import logger

from engine.ml.model_trainer import ModelTrainer


class Signal(str, Enum):
    STRONG_LONG = "strong_long"
    LONG = "long"
    HOLD = "hold"
    SHORT = "short"
    STRONG_SHORT = "strong_short"


@dataclass
class Prediction:
    """ML prediction result."""

    probability: float  # P(up) 0.0 - 1.0
    signal: Signal
    confidence: float  # distance from 0.5 (0.0 - 0.5)
    direction: int  # 1=up, 0=neutral, -1=down

    def to_dict(self) -> dict:
        return {
            "probability": round(self.probability, 4),
            "signal": self.signal.value,
            "confidence": round(self.confidence, 4),
            "direction": self.direction,
        }


class Predictor:
    """Load trained model and produce live predictions.

    Signal thresholds:
        - confidence > 0.65  → strong signal (STRONG_LONG / STRONG_SHORT)
        - confidence > 0.55  → signal (LONG / SHORT)
        - 0.45 - 0.55       → HOLD
        - < 0.45             → weak opposite
    """

    HIGH_CONF_THRESHOLD = 0.65
    MED_CONF_THRESHOLD = 0.55
    LOW_CONF_THRESHOLD = 0.45

    def __init__(self, trainer: Optional[ModelTrainer] = None) -> None:
        self._trainer = trainer or ModelTrainer()
        if not self._trainer.is_trained:
            loaded = self._trainer.load_models()
            if not loaded:
                logger.warning("No trained model found. Predictions will return HOLD.")

    def predict(self, df: pd.DataFrame) -> Prediction:
        """Generate prediction from live OHLCV data.

        Parameters
        ----------
        df : pd.DataFrame
            Recent OHLCV data (at least 200 rows recommended for feature calc).

        Returns
        -------
        Prediction with signal, confidence, and direction.
        """
        if not self._trainer.is_trained:
            return Prediction(
                probability=0.5,
                signal=Signal.HOLD,
                confidence=0.0,
                direction=0,
            )

        try:
            prob = self._trainer.predict_proba(df)
        except Exception as e:
            logger.error("Prediction failed: {}", e)
            return Prediction(
                probability=0.5,
                signal=Signal.HOLD,
                confidence=0.0,
                direction=0,
            )

        confidence = abs(prob - 0.5)
        signal = self._classify_signal(prob)
        direction = 1 if prob > 0.5 else (-1 if prob < 0.5 else 0)

        prediction = Prediction(
            probability=prob,
            signal=signal,
            confidence=confidence,
            direction=direction,
        )

        logger.debug(
            "Prediction: prob={:.4f} signal={} conf={:.4f}",
            prob, signal.value, confidence,
        )
        return prediction

    def _classify_signal(self, prob: float) -> Signal:
        if prob >= self.HIGH_CONF_THRESHOLD:
            return Signal.STRONG_LONG
        elif prob >= self.MED_CONF_THRESHOLD:
            return Signal.LONG
        elif prob > self.LOW_CONF_THRESHOLD:
            return Signal.HOLD
        elif prob > (1 - self.HIGH_CONF_THRESHOLD):
            return Signal.SHORT
        else:
            return Signal.STRONG_SHORT

    def reload_model(self) -> bool:
        """Reload model from disk (after retraining)."""
        return self._trainer.load_models()

    @property
    def is_ready(self) -> bool:
        return self._trainer.is_trained
