"""OHLCV data feed with caching and DataFrame conversion."""

from __future__ import annotations

from typing import Optional

import pandas as pd
from loguru import logger

from engine.config import TradingConfig
from engine.core.exchange_manager import ExchangeManager
from engine.core.market_data_cache import MarketDataCache

OHLCV_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]


class DataFeed:
    """Fetches OHLCV data, caches results, returns pandas DataFrames."""

    def __init__(
        self,
        exchange_manager: ExchangeManager,
        config: TradingConfig,
        cache: Optional[MarketDataCache] = None,
    ) -> None:
        self._em = exchange_manager
        self._config = config
        self._cache = cache or MarketDataCache(ttl_sec=config.cache_ttl_sec)

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1h",
        limit: int = 0,
        exchange: Optional[str] = None,
    ) -> pd.DataFrame:
        limit = limit or self._config.ohlcv_limit
        cache_key = f"ohlcv:{exchange or self._config.default_exchange}:{symbol}:{timeframe}:{limit}"

        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        raw = await self._em.fetch_ohlcv(symbol, timeframe, limit, exchange)
        df = self._to_dataframe(raw)
        self._cache.set(cache_key, df)
        logger.debug("Fetched {} candles for {} {}", len(df), symbol, timeframe)
        return df

    async def fetch_multi_timeframe(
        self,
        symbol: str,
        timeframes: list[str],
        limit: int = 0,
        exchange: Optional[str] = None,
    ) -> dict[str, pd.DataFrame]:
        results: dict[str, pd.DataFrame] = {}
        for tf in timeframes:
            results[tf] = await self.fetch_ohlcv(symbol, tf, limit, exchange)
        return results

    @staticmethod
    def _to_dataframe(raw: list[list]) -> pd.DataFrame:
        if not raw:
            return pd.DataFrame(columns=OHLCV_COLUMNS)
        df = pd.DataFrame(raw, columns=OHLCV_COLUMNS)
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df.set_index("timestamp", inplace=True)
        df = df.astype(float)
        return df
