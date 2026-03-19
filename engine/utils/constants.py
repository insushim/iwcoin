"""Constants and enumerations."""

from __future__ import annotations

from enum import Enum


class Regime(str, Enum):
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"
    VOLATILE = "volatile"
    UNKNOWN = "unknown"


class Side(str, Enum):
    LONG = "long"
    SHORT = "short"
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP_LOSS = "stop_loss"
    STOP_LIMIT = "stop_limit"
    TAKE_PROFIT = "take_profit"
    TRAILING_STOP = "trailing_stop"


class OrderStatus(str, Enum):
    PENDING = "pending"
    OPEN = "open"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    FAILED = "failed"


class PositionStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"


# ── Timeframes ────────────────────────────────────────────────────────────

TIMEFRAMES = [
    "1m", "3m", "5m", "15m", "30m",
    "1h", "2h", "4h", "6h", "8h", "12h",
    "1d", "3d", "1w", "1M",
]

# ── Supported Exchanges ──────────────────────────────────────────────────

SUPPORTED_EXCHANGES = ["binance", "upbit", "bybit", "okx", "bitget"]

# ── Default configs ──────────────────────────────────────────────────────

DEFAULT_OHLCV_LIMIT = 500
DEFAULT_RETRY_COUNT = 3
DEFAULT_RETRY_BACKOFF_BASE = 1.0  # seconds
DEFAULT_CACHE_TTL_SEC = 10
DEFAULT_MAX_SLIPPAGE_PCT = 0.005
