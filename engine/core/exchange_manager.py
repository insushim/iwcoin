"""CCXT multi-exchange manager with retry logic and DRY_RUN support."""

from __future__ import annotations

import asyncio
from typing import Any, Optional

import ccxt.async_support as ccxt
from loguru import logger

from engine.config import TradingConfig, ExchangeCredentials
from engine.utils.constants import SUPPORTED_EXCHANGES, DEFAULT_RETRY_COUNT, DEFAULT_RETRY_BACKOFF_BASE


class ExchangeManager:
    """Manages connections to multiple exchanges via CCXT async."""

    def __init__(self, config: TradingConfig) -> None:
        self._config = config
        self._exchanges: dict[str, ccxt.Exchange] = {}

    # ── Connection ────────────────────────────────────────────────────

    async def connect_all(self) -> None:
        """Initialise and load markets for every configured exchange."""
        for cred in self._config.exchanges:
            await self._connect_one(cred)
        logger.info(
            "Connected exchanges: {}", list(self._exchanges.keys())
        )

    async def _connect_one(self, cred: ExchangeCredentials) -> None:
        name = cred.name.lower()
        if name not in SUPPORTED_EXCHANGES:
            logger.warning("Unsupported exchange '{}', skipping", name)
            return

        cls = getattr(ccxt, name, None)
        if cls is None:
            logger.warning("CCXT has no class for '{}', skipping", name)
            return

        params: dict[str, Any] = {
            "apiKey": cred.api_key,
            "secret": cred.secret,
            "enableRateLimit": True,
        }
        if cred.password:
            params["password"] = cred.password
        if cred.sandbox:
            params["sandbox"] = True

        exchange: ccxt.Exchange = cls(params)
        if cred.sandbox:
            exchange.set_sandbox_mode(True)

        await self._retry(exchange.load_markets)
        self._exchanges[name] = exchange
        logger.info("Connected to {} (sandbox={})", name, cred.sandbox)

    def get_exchange(self, name: Optional[str] = None) -> ccxt.Exchange:
        name = (name or self._config.default_exchange).lower()
        if name not in self._exchanges:
            raise KeyError(f"Exchange '{name}' not connected. Available: {list(self._exchanges.keys())}")
        return self._exchanges[name]

    # ── Data Methods ──────────────────────────────────────────────────

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1h",
        limit: int = 500,
        exchange: Optional[str] = None,
    ) -> list[list]:
        ex = self.get_exchange(exchange)
        return await self._retry(ex.fetch_ohlcv, symbol, timeframe, limit=limit)

    async def fetch_ticker(
        self,
        symbol: str,
        exchange: Optional[str] = None,
    ) -> dict[str, Any]:
        ex = self.get_exchange(exchange)
        return await self._retry(ex.fetch_ticker, symbol)

    async def fetch_balance(
        self,
        exchange: Optional[str] = None,
    ) -> dict[str, Any]:
        if self._config.dry_run:
            return self._paper_balance()
        ex = self.get_exchange(exchange)
        return await self._retry(ex.fetch_balance)

    async def fetch_order_book(
        self,
        symbol: str,
        limit: int = 20,
        exchange: Optional[str] = None,
    ) -> dict[str, Any]:
        ex = self.get_exchange(exchange)
        return await self._retry(ex.fetch_order_book, symbol, limit)

    async def create_order(
        self,
        symbol: str,
        order_type: str,
        side: str,
        amount: float,
        price: Optional[float] = None,
        params: Optional[dict] = None,
        exchange: Optional[str] = None,
    ) -> dict[str, Any]:
        if self._config.dry_run:
            return self._paper_order(symbol, order_type, side, amount, price)

        ex = self.get_exchange(exchange)
        return await self._retry(
            ex.create_order, symbol, order_type, side, amount, price, params or {}
        )

    async def cancel_order(
        self,
        order_id: str,
        symbol: str,
        exchange: Optional[str] = None,
    ) -> dict[str, Any]:
        if self._config.dry_run:
            logger.info("[DRY_RUN] Cancel order {} for {}", order_id, symbol)
            return {"id": order_id, "status": "cancelled"}
        ex = self.get_exchange(exchange)
        return await self._retry(ex.cancel_order, order_id, symbol)

    # ── Cleanup ───────────────────────────────────────────────────────

    async def close_all(self) -> None:
        for name, ex in self._exchanges.items():
            try:
                await ex.close()
            except Exception:
                logger.warning("Error closing exchange {}", name)
        self._exchanges.clear()

    # ── Retry ─────────────────────────────────────────────────────────

    async def _retry(self, coro_func, *args, **kwargs) -> Any:
        retries = self._config.retry_count or DEFAULT_RETRY_COUNT
        backoff = self._config.retry_backoff_base or DEFAULT_RETRY_BACKOFF_BASE

        last_exc: Optional[Exception] = None
        for attempt in range(1, retries + 1):
            try:
                return await coro_func(*args, **kwargs)
            except (ccxt.NetworkError, ccxt.ExchangeNotAvailable, ccxt.RequestTimeout) as exc:
                last_exc = exc
                wait = backoff * (2 ** (attempt - 1))
                logger.warning(
                    "Retry {}/{} for {} after {:.1f}s – {}",
                    attempt, retries, coro_func.__name__, wait, exc,
                )
                await asyncio.sleep(wait)
            except ccxt.BaseError:
                raise
        raise last_exc  # type: ignore[misc]

    # ── Paper helpers ─────────────────────────────────────────────────

    def _paper_balance(self) -> dict[str, Any]:
        usdt = self._config.paper_balance_usdt
        return {
            "total": {"USDT": usdt},
            "free": {"USDT": usdt},
            "used": {"USDT": 0.0},
        }

    @staticmethod
    def _paper_order(
        symbol: str, order_type: str, side: str, amount: float, price: Optional[float]
    ) -> dict[str, Any]:
        import uuid

        order_id = f"paper-{uuid.uuid4().hex[:12]}"
        logger.info(
            "[DRY_RUN] {} {} {} amount={} price={}",
            order_type.upper(), side.upper(), symbol, amount, price,
        )
        return {
            "id": order_id,
            "symbol": symbol,
            "type": order_type,
            "side": side,
            "amount": amount,
            "price": price,
            "status": "filled" if order_type == "market" else "open",
            "dry_run": True,
        }
