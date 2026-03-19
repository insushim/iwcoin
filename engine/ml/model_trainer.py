"""LightGBM + XGBoost ensemble trainer with periodic retraining."""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import joblib
import numpy as np
import pandas as pd
from loguru import logger

try:
    import lightgbm as lgb
except ImportError:
    lgb = None  # type: ignore[assignment]

try:
    import xgboost as xgb
except ImportError:
    xgb = None  # type: ignore[assignment]

from engine.ml.feature_factory import create_features


_MODEL_DIR = Path(__file__).resolve().parent / "models"
_MODEL_DIR.mkdir(parents=True, exist_ok=True)

# Feature columns to exclude from training
_EXCLUDE_COLS = {"open", "high", "low", "close", "volume", "timestamp", "target"}


class ModelTrainer:
    """LightGBM (0.6) + XGBoost (0.4) ensemble classifier."""

    RETRAIN_INTERVAL_SEC: int = 6 * 3600  # 6 hours

    def __init__(
        self,
        lgb_params: Optional[dict[str, Any]] = None,
        xgb_params: Optional[dict[str, Any]] = None,
        lgb_weight: float = 0.6,
        xgb_weight: float = 0.4,
        model_dir: Optional[Path] = None,
    ) -> None:
        self._model_dir = model_dir or _MODEL_DIR

        self._lgb_params: dict[str, Any] = lgb_params or {
            "objective": "binary",
            "metric": "binary_logloss",
            "n_estimators": 500,
            "max_depth": 6,
            "learning_rate": 0.03,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "min_child_samples": 20,
            "reg_alpha": 0.1,
            "reg_lambda": 1.0,
            "verbose": -1,
            "n_jobs": -1,
            "random_state": 42,
        }
        self._xgb_params: dict[str, Any] = xgb_params or {
            "objective": "binary:logistic",
            "eval_metric": "logloss",
            "n_estimators": 300,
            "max_depth": 5,
            "learning_rate": 0.05,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "min_child_weight": 5,
            "reg_alpha": 0.1,
            "reg_lambda": 1.0,
            "verbosity": 0,
            "n_jobs": -1,
            "random_state": 42,
        }

        self._lgb_weight = lgb_weight
        self._xgb_weight = xgb_weight

        self._lgb_model: Any = None
        self._xgb_model: Any = None
        self._feature_names: list[str] = []
        self._last_train_time: float = 0.0
        self._accuracy_history: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def train(self, df: pd.DataFrame, target_periods: int = 5) -> dict[str, float]:
        """Train ensemble on OHLCV DataFrame.

        Returns dict with training metrics.
        """
        featured = create_features(df, target_periods=target_periods, include_target=True)
        featured = featured.dropna(subset=["target"])

        feature_cols = [c for c in featured.columns if c not in _EXCLUDE_COLS]
        X = featured[feature_cols].replace([np.inf, -np.inf], np.nan).fillna(0)
        y = featured["target"].astype(int)

        if len(X) < 100:
            raise ValueError(f"Insufficient data for training: {len(X)} rows")

        # Train / validation split (last 20% for validation)
        split_idx = int(len(X) * 0.8)
        X_train, X_val = X.iloc[:split_idx], X.iloc[split_idx:]
        y_train, y_val = y.iloc[:split_idx], y.iloc[split_idx:]

        self._feature_names = list(X.columns)
        metrics: dict[str, float] = {}

        # LightGBM
        if lgb is not None:
            self._lgb_model = lgb.LGBMClassifier(**self._lgb_params)
            self._lgb_model.fit(
                X_train, y_train,
                eval_set=[(X_val, y_val)],
            )
            lgb_pred = self._lgb_model.predict(X_val)
            metrics["lgb_accuracy"] = float((lgb_pred == y_val).mean())
            logger.info("LightGBM val accuracy: {:.4f}", metrics["lgb_accuracy"])
        else:
            logger.warning("LightGBM not installed, skipping")

        # XGBoost
        if xgb is not None:
            self._xgb_model = xgb.XGBClassifier(**self._xgb_params)
            self._xgb_model.fit(
                X_train, y_train,
                eval_set=[(X_val, y_val)],
                verbose=False,
            )
            xgb_pred = self._xgb_model.predict(X_val)
            metrics["xgb_accuracy"] = float((xgb_pred == y_val).mean())
            logger.info("XGBoost val accuracy: {:.4f}", metrics["xgb_accuracy"])
        else:
            logger.warning("XGBoost not installed, skipping")

        # Ensemble accuracy
        if self._lgb_model and self._xgb_model:
            lgb_prob = self._lgb_model.predict_proba(X_val)[:, 1]
            xgb_prob = self._xgb_model.predict_proba(X_val)[:, 1]
            ens_prob = self._lgb_weight * lgb_prob + self._xgb_weight * xgb_prob
            ens_pred = (ens_prob > 0.5).astype(int)
            metrics["ensemble_accuracy"] = float((ens_pred == y_val).mean())
            logger.info("Ensemble val accuracy: {:.4f}", metrics["ensemble_accuracy"])

        metrics["train_rows"] = float(len(X_train))
        metrics["val_rows"] = float(len(X_val))
        metrics["n_features"] = float(len(self._feature_names))

        self._last_train_time = time.time()
        self._accuracy_history.append({
            "timestamp": datetime.utcnow().isoformat(),
            **metrics,
        })

        self.save_models()
        return metrics

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save_models(self) -> None:
        """Save models and metadata to disk."""
        if self._lgb_model:
            joblib.dump(self._lgb_model, self._model_dir / "lgb_model.joblib")
        if self._xgb_model:
            joblib.dump(self._xgb_model, self._model_dir / "xgb_model.joblib")
        joblib.dump({
            "feature_names": self._feature_names,
            "lgb_weight": self._lgb_weight,
            "xgb_weight": self._xgb_weight,
            "last_train_time": self._last_train_time,
        }, self._model_dir / "meta.joblib")
        logger.info("Models saved to {}", self._model_dir)

    def load_models(self) -> bool:
        """Load models from disk. Returns True if successful."""
        try:
            meta_path = self._model_dir / "meta.joblib"
            if not meta_path.exists():
                return False

            meta = joblib.load(meta_path)
            self._feature_names = meta["feature_names"]
            self._lgb_weight = meta["lgb_weight"]
            self._xgb_weight = meta["xgb_weight"]
            self._last_train_time = meta.get("last_train_time", 0.0)

            lgb_path = self._model_dir / "lgb_model.joblib"
            if lgb_path.exists():
                self._lgb_model = joblib.load(lgb_path)

            xgb_path = self._model_dir / "xgb_model.joblib"
            if xgb_path.exists():
                self._xgb_model = joblib.load(xgb_path)

            logger.info("Models loaded ({} features)", len(self._feature_names))
            return True
        except Exception as e:
            logger.error("Failed to load models: {}", e)
            return False

    # ------------------------------------------------------------------
    # Prediction
    # ------------------------------------------------------------------

    def predict_proba(self, df: pd.DataFrame) -> float:
        """Return ensemble probability of upward move (0.0 - 1.0)."""
        featured = create_features(df, include_target=False)
        featured = featured.replace([np.inf, -np.inf], np.nan).fillna(0)

        # Align features
        for col in self._feature_names:
            if col not in featured.columns:
                featured[col] = 0.0
        X = featured[self._feature_names].iloc[[-1]]

        probs: list[float] = []
        weights: list[float] = []

        if self._lgb_model is not None:
            probs.append(float(self._lgb_model.predict_proba(X)[0, 1]))
            weights.append(self._lgb_weight)
        if self._xgb_model is not None:
            probs.append(float(self._xgb_model.predict_proba(X)[0, 1]))
            weights.append(self._xgb_weight)

        if not probs:
            return 0.5

        total_w = sum(weights)
        return sum(p * w for p, w in zip(probs, weights)) / total_w

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def needs_retrain(self) -> bool:
        """Check if retraining is due."""
        return (time.time() - self._last_train_time) > self.RETRAIN_INTERVAL_SEC

    @property
    def is_trained(self) -> bool:
        return self._lgb_model is not None or self._xgb_model is not None

    @property
    def accuracy_history(self) -> list[dict[str, Any]]:
        return list(self._accuracy_history)

    def feature_importance(self, top_n: int = 20) -> list[tuple[str, float]]:
        """Return top-N features by average importance."""
        importance: dict[str, float] = {}
        count: dict[str, int] = {}

        if self._lgb_model is not None and hasattr(self._lgb_model, "feature_importances_"):
            for name, imp in zip(self._feature_names, self._lgb_model.feature_importances_):
                importance[name] = importance.get(name, 0.0) + float(imp)
                count[name] = count.get(name, 0) + 1

        if self._xgb_model is not None and hasattr(self._xgb_model, "feature_importances_"):
            for name, imp in zip(self._feature_names, self._xgb_model.feature_importances_):
                importance[name] = importance.get(name, 0.0) + float(imp)
                count[name] = count.get(name, 0) + 1

        avg = {k: importance[k] / count[k] for k in importance}
        return sorted(avg.items(), key=lambda x: x[1], reverse=True)[:top_n]
