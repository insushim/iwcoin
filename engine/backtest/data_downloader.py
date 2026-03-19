"""Download and cache OHLCV data from exchanges via CCXT."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Optional

import ccxt.async_support as ccxt
import pandas as pd
from loguru import logger


_CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _cache_path(symbol: str, timeframe: str) -> Path:
    safe_symbol = symbol.replace("/", "_").replace(":", "_")
    return _CACHE_DIR / f"{safe_symbol}_{timeframe}.csv"


class DataDownloader:
    """Download OHLCV from exchanges and cache as CSV."""

    def __init__(
        self,
        exchange_id: str = "binance",
        cache_dir: Optional[Path] = None,
    ) -> None:
        self._exchange_id = exchange_id
        self._cache_dir = cache_dir or _CACHE_DIR
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    async def download(
        self,
        symbol: str,
        timeframe: str = "1h",
        since: Optional[str] = None,
        limit: int = 1000,
        use_cache: bool = True,
    ) -> pd.DataFrame:
        """Download OHLCV data, optionally using cached CSV.

        Parameters
        ----------
        symbol : str
            Trading pair, e.g. "BTC/USDT".
        timeframe : str
            Candle interval, e.g. "1h", "4h", "1d".
        since : str, optional
            Start date as ISO string, e.g. "2024-01-01".
        limit : int
            Max candles per request (exchange may cap this).
        use_cache : bool
            If True, return cached data if available and append new.

        Returns
        -------
        pd.DataFrame with columns: timestamp, open, high, low, close, volume.
        """
        cache_file = self._cache_dir / _cache_path(symbol, timeframe).name

        existing_df: Optional[pd.DataFrame] = None
        if use_cache and cache_file.exists():
            try:
                existing_df = pd.read_csv(cache_file, parse_dates=["timestamp"])
                logger.debug(
                    "Cache hit for {} {}: {} rows",
                    symbol, timeframe, len(existing_df),
                )
            except Exception:
                existing_df = None

        since_ms: Optional[int] = None
        if since:
            since_ms = int(pd.Timestamp(since).timestamp() * 1000)
        elif existing_df is not None and len(existing_df) > 0:
            # Fetch from last cached timestamp
            last_ts = existing_df["timestamp"].max()
            since_ms = int(pd.Timestamp(last_ts).timestamp() * 1000) + 1

        exchange = getattr(ccxt, self._exchange_id)({
            "enableRateLimit": True,
        })

        all_candles: list[list] = []
        try:
            fetch_since = since_ms
            while True:
                candles = await exchange.fetch_ohlcv(
                    symbol, timeframe, since=fetch_since, limit=limit
                )
                if not candles:
                    break
                all_candles.extend(candles)
                logger.debug(
                    "Fetched {} candles for {} {} (total: {})",
                    len(candles), symbol, timeframe, len(all_candles),
                )
                if len(candles) < limit:
                    break
                # Move to next batch
                fetch_since = candles[-1][0] + 1
                await asyncio.sleep(exchange.rateLimit / 1000.0)
        finally:
            await exchange.close()

        if not all_candles:
            if existing_df is not None:
                return existing_df
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

        new_df = pd.DataFrame(
            all_candles,
            columns=["timestamp", "open", "high", "low", "close", "volume"],
        )
        new_df["timestamp"] = pd.to_datetime(new_df["timestamp"], unit="ms")

        # Merge with existing cache
        if existing_df is not None and len(existing_df) > 0:
            combined = pd.concat([existing_df, new_df], ignore_index=True)
            combined = combined.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
        else:
            combined = new_df.sort_values("timestamp").reset_index(drop=True)

        # Save to cache
        combined.to_csv(cache_file, index=False)
        logger.info(
            "Cached {} rows for {} {} at {}",
            len(combined), symbol, timeframe, cache_file,
        )
        return combined

    async def download_multiple(
        self,
        symbols: list[str],
        timeframes: list[str],
        since: Optional[str] = None,
        limit: int = 1000,
    ) -> dict[str, pd.DataFrame]:
        """Download data for multiple symbol/timeframe combinations.

        Returns dict keyed by "SYMBOL_TIMEFRAME".
        """
        results: dict[str, pd.DataFrame] = {}
        for symbol in symbols:
            for tf in timeframes:
                key = f"{symbol.replace('/', '_')}_{tf}"
                try:
                    df = await self.download(symbol, tf, since=since, limit=limit)
                    results[key] = df
                except Exception as e:
                    logger.error("Failed to download {} {}: {}", symbol, tf, e)
        return results

    def load_cached(self, symbol: str, timeframe: str) -> Optional[pd.DataFrame]:
        """Load cached CSV data without downloading."""
        cache_file = self._cache_dir / _cache_path(symbol, timeframe).name
        if not cache_file.exists():
            return None
        try:
            return pd.read_csv(cache_file, parse_dates=["timestamp"])
        except Exception as e:
            logger.error("Failed to load cache {}: {}", cache_file, e)
            return None

    def list_cached(self) -> list[str]:
        """List all cached data files."""
        return [f.stem for f in self._cache_dir.glob("*.csv")]
