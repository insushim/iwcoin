"""Walk-forward optimization with sliding window train/test splits."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
import pandas as pd
from loguru import logger

from engine.ml.model_trainer import ModelTrainer


@dataclass
class WalkForwardResult:
    """Aggregate out-of-sample performance across all folds."""

    fold_results: list[dict[str, Any]] = field(default_factory=list)
    oos_accuracy: float = 0.0
    oos_precision: float = 0.0
    oos_recall: float = 0.0
    oos_f1: float = 0.0
    oos_log_loss: float = 0.0
    mean_confidence: float = 0.0
    n_folds: int = 0

    def summary(self) -> dict[str, Any]:
        return {
            "n_folds": self.n_folds,
            "oos_accuracy": round(self.oos_accuracy, 4),
            "oos_precision": round(self.oos_precision, 4),
            "oos_recall": round(self.oos_recall, 4),
            "oos_f1": round(self.oos_f1, 4),
            "oos_log_loss": round(self.oos_log_loss, 4),
            "mean_confidence": round(self.mean_confidence, 4),
        }


class WalkForwardOptimizer:
    """Sliding window walk-forward analysis for realistic OOS estimation.

    Parameters
    ----------
    train_window : int
        Number of rows for each training window (default 500).
    test_window : int
        Number of rows for each test window (default 100).
    step_size : int
        How many rows to slide forward each fold (default 100).
    target_periods : int
        Number of future candles for the target label.
    """

    def __init__(
        self,
        train_window: int = 500,
        test_window: int = 100,
        step_size: int = 100,
        target_periods: int = 5,
    ) -> None:
        self._train_window = train_window
        self._test_window = test_window
        self._step_size = step_size
        self._target_periods = target_periods

    def run(
        self,
        df: pd.DataFrame,
        lgb_params: Optional[dict[str, Any]] = None,
        xgb_params: Optional[dict[str, Any]] = None,
    ) -> WalkForwardResult:
        """Execute walk-forward optimization.

        Parameters
        ----------
        df : pd.DataFrame
            Full OHLCV dataset (must have open, high, low, close, volume).

        Returns
        -------
        WalkForwardResult with aggregated OOS metrics.
        """
        total_needed = self._train_window + self._test_window
        if len(df) < total_needed:
            raise ValueError(
                f"Need at least {total_needed} rows, got {len(df)}"
            )

        fold_results: list[dict[str, Any]] = []
        all_y_true: list[int] = []
        all_y_prob: list[float] = []

        start = 0
        fold_idx = 0

        while start + total_needed <= len(df):
            train_end = start + self._train_window
            test_end = train_end + self._test_window
            if test_end > len(df):
                break

            train_df = df.iloc[start:train_end].copy()
            test_df = df.iloc[start:test_end].copy()  # include train for feature calculation

            fold_idx += 1
            logger.debug(
                "Fold {}: train [{}-{}], test [{}-{}]",
                fold_idx, start, train_end, train_end, test_end,
            )

            try:
                trainer = ModelTrainer(
                    lgb_params=lgb_params,
                    xgb_params=xgb_params,
                )
                metrics = trainer.train(train_df, target_periods=self._target_periods)

                # Predict on test set
                from engine.ml.feature_factory import create_features, _EXCLUDE_COLS  # noqa: F811

                featured = create_features(test_df, target_periods=self._target_periods, include_target=True)
                featured = featured.dropna(subset=["target"])
                # Only use the test portion rows
                featured = featured.iloc[self._train_window:]

                if len(featured) == 0:
                    start += self._step_size
                    continue

                exclude = {"open", "high", "low", "close", "volume", "timestamp", "target"}
                feature_cols = [c for c in featured.columns if c not in exclude]
                X_test = featured[feature_cols].replace([np.inf, -np.inf], np.nan).fillna(0)
                y_test = featured["target"].astype(int)

                # Align features
                for col in trainer._feature_names:
                    if col not in X_test.columns:
                        X_test[col] = 0.0
                X_test = X_test[trainer._feature_names]

                # Get ensemble probabilities
                probs: list[float] = []
                for i in range(len(X_test)):
                    row = X_test.iloc[[i]]
                    p_list = []
                    w_list = []
                    if trainer._lgb_model is not None:
                        p_list.append(float(trainer._lgb_model.predict_proba(row)[0, 1]))
                        w_list.append(trainer._lgb_weight)
                    if trainer._xgb_model is not None:
                        p_list.append(float(trainer._xgb_model.predict_proba(row)[0, 1]))
                        w_list.append(trainer._xgb_weight)
                    if p_list:
                        prob = sum(p * w for p, w in zip(p_list, w_list)) / sum(w_list)
                    else:
                        prob = 0.5
                    probs.append(prob)

                y_pred = [1 if p > 0.5 else 0 for p in probs]
                y_true_list = y_test.tolist()

                acc = sum(1 for a, b in zip(y_pred, y_true_list) if a == b) / len(y_pred)

                fold_result = {
                    "fold": fold_idx,
                    "train_start": start,
                    "train_end": train_end,
                    "test_start": train_end,
                    "test_end": test_end,
                    "accuracy": acc,
                    "n_test": len(y_pred),
                    **metrics,
                }
                fold_results.append(fold_result)
                all_y_true.extend(y_true_list)
                all_y_prob.extend(probs)

            except Exception as e:
                logger.warning("Fold {} failed: {}", fold_idx, e)

            start += self._step_size

        if not fold_results:
            logger.warning("No successful folds in walk-forward")
            return WalkForwardResult()

        # Aggregate OOS metrics
        y_true = np.array(all_y_true)
        y_prob = np.array(all_y_prob)
        y_pred = (y_prob > 0.5).astype(int)

        tp = int(((y_pred == 1) & (y_true == 1)).sum())
        fp = int(((y_pred == 1) & (y_true == 0)).sum())
        fn = int(((y_pred == 0) & (y_true == 1)).sum())

        accuracy = float((y_pred == y_true).mean())
        precision = tp / max(tp + fp, 1)
        recall = tp / max(tp + fn, 1)
        f1 = 2 * precision * recall / max(precision + recall, 1e-10)

        # Log loss
        eps = 1e-15
        y_prob_clipped = np.clip(y_prob, eps, 1 - eps)
        log_loss = -float(np.mean(
            y_true * np.log(y_prob_clipped) + (1 - y_true) * np.log(1 - y_prob_clipped)
        ))

        mean_conf = float(np.mean(np.abs(y_prob - 0.5)) + 0.5)

        result = WalkForwardResult(
            fold_results=fold_results,
            oos_accuracy=accuracy,
            oos_precision=precision,
            oos_recall=recall,
            oos_f1=f1,
            oos_log_loss=log_loss,
            mean_confidence=mean_conf,
            n_folds=len(fold_results),
        )

        logger.info(
            "Walk-forward complete: {} folds, OOS accuracy={:.4f}, F1={:.4f}",
            result.n_folds, accuracy, f1,
        )
        return result
