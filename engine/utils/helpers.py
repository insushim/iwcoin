"""Common helper functions."""

from __future__ import annotations

import math
from datetime import datetime, timezone, timedelta
from typing import Optional

KST = timezone(timedelta(hours=9))


# ── Rounding ──────────────────────────────────────────────────────────────

def round_price(price: float, tick_size: float = 0.01) -> float:
    """Round price to the nearest tick size."""
    if tick_size <= 0:
        return price
    precision = max(0, -int(math.floor(math.log10(tick_size))))
    return round(round(price / tick_size) * tick_size, precision)


def round_amount(amount: float, step_size: float = 0.001) -> float:
    """Round order amount down to the nearest step size (floor)."""
    if step_size <= 0:
        return amount
    precision = max(0, -int(math.floor(math.log10(step_size))))
    return round(math.floor(amount / step_size) * step_size, precision)


# ── P/L ───────────────────────────────────────────────────────────────────

def calculate_pnl(
    entry_price: float,
    current_price: float,
    amount: float,
    side: str = "long",
) -> float:
    """Calculate unrealised P/L in quote currency."""
    if side.lower() == "long":
        return (current_price - entry_price) * amount
    return (entry_price - current_price) * amount


def calculate_pnl_pct(
    entry_price: float,
    current_price: float,
    side: str = "long",
) -> float:
    """Calculate P/L percentage."""
    if entry_price == 0:
        return 0.0
    if side.lower() == "long":
        return (current_price - entry_price) / entry_price
    return (entry_price - current_price) / entry_price


# ── Timestamp / Time ──────────────────────────────────────────────────────

def ts_to_datetime(ts_ms: int) -> datetime:
    """Millisecond UNIX timestamp → UTC datetime."""
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)


def datetime_to_ts(dt: datetime) -> int:
    """Datetime → millisecond UNIX timestamp."""
    return int(dt.timestamp() * 1000)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_kst() -> datetime:
    return datetime.now(KST)


def to_kst(dt: Optional[datetime] = None) -> datetime:
    """Convert datetime to KST. If None, return current KST."""
    if dt is None:
        return now_kst()
    return dt.astimezone(KST)


def format_kst(dt: Optional[datetime] = None, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    return to_kst(dt).strftime(fmt)
