"""Configuration management for the trading bot engine."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load .env from project root
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)


def _bool(val: Optional[str], default: bool = False) -> bool:
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes")


def _float(val: Optional[str], default: float = 0.0) -> float:
    if val is None:
        return default
    try:
        return float(val)
    except ValueError:
        return default


def _int(val: Optional[str], default: int = 0) -> int:
    if val is None:
        return default
    try:
        return int(val)
    except ValueError:
        return default


@dataclass
class ExchangeCredentials:
    name: str
    api_key: str = ""
    secret: str = ""
    password: str = ""  # OKX passphrase, etc.
    sandbox: bool = False


@dataclass
class TradingConfig:
    # ── Mode ──────────────────────────────────────────────
    dry_run: bool = True
    paper_balance_usdt: float = 10_000.0

    # ── Exchange ──────────────────────────────────────────
    default_exchange: str = "binance"
    exchanges: list[ExchangeCredentials] = field(default_factory=list)

    # ── Risk ──────────────────────────────────────────────
    max_position_pct: float = 0.1       # 10% of equity per position
    max_open_positions: int = 5
    default_stop_loss_pct: float = 0.02  # 2%
    default_take_profit_pct: float = 0.04  # 4%
    trailing_stop_pct: float = 0.01      # 1%
    max_slippage_pct: float = 0.005      # 0.5%

    # ── Order ─────────────────────────────────────────────
    default_order_type: str = "limit"
    limit_order_timeout_sec: int = 30
    retry_count: int = 3
    retry_backoff_base: float = 1.0

    # ── Data ──────────────────────────────────────────────
    default_timeframe: str = "1h"
    ohlcv_limit: int = 500
    cache_ttl_sec: int = 10

    # ── Notification ──────────────────────────────────────
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # ── Logging ───────────────────────────────────────────
    log_level: str = "INFO"
    log_dir: str = "logs"


def _load_exchanges() -> list[ExchangeCredentials]:
    """Load exchange credentials from env vars.

    Pattern: EXCHANGE_{NAME}_API_KEY, EXCHANGE_{NAME}_SECRET, etc.
    """
    names = [
        s.strip()
        for s in os.getenv("EXCHANGES", "binance").split(",")
        if s.strip()
    ]
    creds: list[ExchangeCredentials] = []
    for name in names:
        prefix = f"EXCHANGE_{name.upper()}_"
        creds.append(
            ExchangeCredentials(
                name=name.lower(),
                api_key=os.getenv(f"{prefix}API_KEY", ""),
                secret=os.getenv(f"{prefix}SECRET", ""),
                password=os.getenv(f"{prefix}PASSWORD", ""),
                sandbox=_bool(os.getenv(f"{prefix}SANDBOX")),
            )
        )
    return creds


def load_config() -> TradingConfig:
    """Build TradingConfig from environment variables."""
    return TradingConfig(
        dry_run=_bool(os.getenv("DRY_RUN"), default=True),
        paper_balance_usdt=_float(os.getenv("PAPER_BALANCE_USDT"), 10_000.0),
        default_exchange=os.getenv("DEFAULT_EXCHANGE", "binance"),
        exchanges=_load_exchanges(),
        max_position_pct=_float(os.getenv("MAX_POSITION_PCT"), 0.1),
        max_open_positions=_int(os.getenv("MAX_OPEN_POSITIONS"), 5),
        default_stop_loss_pct=_float(os.getenv("DEFAULT_STOP_LOSS_PCT"), 0.02),
        default_take_profit_pct=_float(os.getenv("DEFAULT_TAKE_PROFIT_PCT"), 0.04),
        trailing_stop_pct=_float(os.getenv("TRAILING_STOP_PCT"), 0.01),
        max_slippage_pct=_float(os.getenv("MAX_SLIPPAGE_PCT"), 0.005),
        default_order_type=os.getenv("DEFAULT_ORDER_TYPE", "limit"),
        limit_order_timeout_sec=_int(os.getenv("LIMIT_ORDER_TIMEOUT_SEC"), 30),
        retry_count=_int(os.getenv("RETRY_COUNT"), 3),
        retry_backoff_base=_float(os.getenv("RETRY_BACKOFF_BASE"), 1.0),
        default_timeframe=os.getenv("DEFAULT_TIMEFRAME", "1h"),
        ohlcv_limit=_int(os.getenv("OHLCV_LIMIT"), 500),
        cache_ttl_sec=_int(os.getenv("CACHE_TTL_SEC"), 10),
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        log_dir=os.getenv("LOG_DIR", "logs"),
    )
