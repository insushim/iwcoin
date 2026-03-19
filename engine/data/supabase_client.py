"""Supabase client for persistent storage of trading data."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Optional

from loguru import logger

try:
    from supabase import create_client, Client as SupabaseSDKClient
except ImportError:
    SupabaseSDKClient = None  # type: ignore[assignment, misc]
    create_client = None  # type: ignore[assignment]


class SupabaseClient:
    """CRUD operations for all trading tables.

    Tables:
        - trades
        - positions
        - regime_history
        - strategy_performance
        - balance_snapshots
        - ml_predictions
        - ensemble_votes
    """

    def __init__(
        self,
        url: Optional[str] = None,
        key: Optional[str] = None,
    ) -> None:
        self._url = url or os.getenv("SUPABASE_URL", "")
        self._key = key or os.getenv("SUPABASE_KEY", "")
        self._client: Optional[Any] = None

    def connect(self) -> bool:
        """Initialize Supabase client."""
        if not self._url or not self._key:
            logger.warning("Supabase URL or KEY not configured")
            return False
        if create_client is None:
            logger.warning("supabase-py not installed")
            return False
        try:
            self._client = create_client(self._url, self._key)
            logger.info("Supabase connected")
            return True
        except Exception as e:
            logger.error("Supabase connection failed: {}", e)
            return False

    @property
    def is_connected(self) -> bool:
        return self._client is not None

    # ------------------------------------------------------------------
    # Generic helpers
    # ------------------------------------------------------------------

    def _insert(self, table: str, data: dict[str, Any]) -> Optional[dict]:
        if not self._client:
            return None
        try:
            result = self._client.table(table).insert(data).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error("Insert to {} failed: {}", table, e)
            return None

    def _batch_insert(self, table: str, rows: list[dict[str, Any]]) -> int:
        """Insert multiple rows. Returns count of successfully inserted."""
        if not self._client or not rows:
            return 0
        try:
            result = self._client.table(table).insert(rows).execute()
            return len(result.data) if result.data else 0
        except Exception as e:
            logger.error("Batch insert to {} failed: {}", table, e)
            return 0

    def _select(
        self,
        table: str,
        filters: Optional[dict[str, Any]] = None,
        order_by: Optional[str] = None,
        limit: Optional[int] = None,
        desc: bool = True,
    ) -> list[dict[str, Any]]:
        if not self._client:
            return []
        try:
            query = self._client.table(table).select("*")
            if filters:
                for k, v in filters.items():
                    query = query.eq(k, v)
            if order_by:
                query = query.order(order_by, desc=desc)
            if limit:
                query = query.limit(limit)
            result = query.execute()
            return result.data or []
        except Exception as e:
            logger.error("Select from {} failed: {}", table, e)
            return []

    def _update(
        self, table: str, filters: dict[str, Any], data: dict[str, Any]
    ) -> Optional[dict]:
        if not self._client:
            return None
        try:
            query = self._client.table(table).update(data)
            for k, v in filters.items():
                query = query.eq(k, v)
            result = query.execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error("Update {} failed: {}", table, e)
            return None

    def _delete(self, table: str, filters: dict[str, Any]) -> bool:
        if not self._client:
            return False
        try:
            query = self._client.table(table).delete()
            for k, v in filters.items():
                query = query.eq(k, v)
            query.execute()
            return True
        except Exception as e:
            logger.error("Delete from {} failed: {}", table, e)
            return False

    # ------------------------------------------------------------------
    # Trades
    # ------------------------------------------------------------------

    def insert_trade(self, trade: dict[str, Any]) -> Optional[dict]:
        trade.setdefault("created_at", datetime.now(timezone.utc).isoformat())
        return self._insert("trades", trade)

    def get_trades(
        self, symbol: Optional[str] = None, limit: int = 100
    ) -> list[dict]:
        filters = {"symbol": symbol} if symbol else None
        return self._select("trades", filters=filters, order_by="created_at", limit=limit)

    def batch_insert_trades(self, trades: list[dict[str, Any]]) -> int:
        for t in trades:
            t.setdefault("created_at", datetime.now(timezone.utc).isoformat())
        return self._batch_insert("trades", trades)

    # ------------------------------------------------------------------
    # Positions
    # ------------------------------------------------------------------

    def insert_position(self, position: dict[str, Any]) -> Optional[dict]:
        position.setdefault("opened_at", datetime.now(timezone.utc).isoformat())
        return self._insert("positions", position)

    def get_open_positions(self) -> list[dict]:
        return self._select("positions", filters={"status": "open"}, order_by="opened_at")

    def update_position(self, position_id: str, data: dict[str, Any]) -> Optional[dict]:
        return self._update("positions", {"id": position_id}, data)

    def close_position(self, position_id: str, close_data: dict[str, Any]) -> Optional[dict]:
        close_data["status"] = "closed"
        close_data.setdefault("closed_at", datetime.now(timezone.utc).isoformat())
        return self._update("positions", {"id": position_id}, close_data)

    # ------------------------------------------------------------------
    # Regime history
    # ------------------------------------------------------------------

    def insert_regime(self, regime: dict[str, Any]) -> Optional[dict]:
        regime.setdefault("detected_at", datetime.now(timezone.utc).isoformat())
        return self._insert("regime_history", regime)

    def get_regime_history(self, limit: int = 50) -> list[dict]:
        return self._select("regime_history", order_by="detected_at", limit=limit)

    # ------------------------------------------------------------------
    # Strategy performance
    # ------------------------------------------------------------------

    def insert_strategy_performance(self, perf: dict[str, Any]) -> Optional[dict]:
        perf.setdefault("recorded_at", datetime.now(timezone.utc).isoformat())
        return self._insert("strategy_performance", perf)

    def get_strategy_performance(
        self, strategy_name: Optional[str] = None, limit: int = 50
    ) -> list[dict]:
        filters = {"strategy_name": strategy_name} if strategy_name else None
        return self._select("strategy_performance", filters=filters, order_by="recorded_at", limit=limit)

    # ------------------------------------------------------------------
    # Balance snapshots
    # ------------------------------------------------------------------

    def insert_balance_snapshot(self, snapshot: dict[str, Any]) -> Optional[dict]:
        snapshot.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        return self._insert("balance_snapshots", snapshot)

    def get_balance_history(self, limit: int = 168) -> list[dict]:  # 7 days hourly
        return self._select("balance_snapshots", order_by="timestamp", limit=limit)

    # ------------------------------------------------------------------
    # ML predictions
    # ------------------------------------------------------------------

    def insert_prediction(self, prediction: dict[str, Any]) -> Optional[dict]:
        prediction.setdefault("predicted_at", datetime.now(timezone.utc).isoformat())
        return self._insert("ml_predictions", prediction)

    def get_predictions(self, limit: int = 100) -> list[dict]:
        return self._select("ml_predictions", order_by="predicted_at", limit=limit)

    def batch_insert_predictions(self, predictions: list[dict[str, Any]]) -> int:
        for p in predictions:
            p.setdefault("predicted_at", datetime.now(timezone.utc).isoformat())
        return self._batch_insert("ml_predictions", predictions)

    # ------------------------------------------------------------------
    # Ensemble votes
    # ------------------------------------------------------------------

    def insert_ensemble_vote(self, vote: dict[str, Any]) -> Optional[dict]:
        vote.setdefault("voted_at", datetime.now(timezone.utc).isoformat())
        return self._insert("ensemble_votes", vote)

    def get_ensemble_votes(self, limit: int = 100) -> list[dict]:
        return self._select("ensemble_votes", order_by="voted_at", limit=limit)

    def batch_insert_ensemble_votes(self, votes: list[dict[str, Any]]) -> int:
        for v in votes:
            v.setdefault("voted_at", datetime.now(timezone.utc).isoformat())
        return self._batch_insert("ensemble_votes", votes)
