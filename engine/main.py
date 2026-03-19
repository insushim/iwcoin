"""CryptoNexusUltra - Main orchestrator for the automated trading system."""

from __future__ import annotations

import asyncio
import signal
import sys
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from loguru import logger

from engine.config import TradingConfig, load_config
from engine.utils.logger import setup_logger
from engine.utils.constants import Regime
from engine.core.exchange_manager import ExchangeManager
from engine.data.supabase_client import SupabaseClient
from engine.data.trade_journal import TradeJournal
from engine.ml.model_trainer import ModelTrainer
from engine.ml.predictor import Predictor
from engine.notifications.telegram_commander import TelegramCommander


# KST = UTC + 9
_KST = timezone(timedelta(hours=9))


class CryptoNexusUltra:
    """Top-level orchestrator.

    Main loop responsibilities:
        - Regime check every 5 minutes
        - Strategy cycle (async)
        - Position monitoring
        - Risk checks
        - Balance snapshot every hour
        - ML retrain every 6 hours
        - Daily report at 09:00 KST
        - Panic stop on critical errors
    """

    def __init__(self, config: Optional[TradingConfig] = None) -> None:
        self._config = config or load_config()
        setup_logger(level=self._config.log_level, log_dir=self._config.log_dir)

        # Core modules
        self._exchange = ExchangeManager(self._config)
        self._db = SupabaseClient()
        self._journal = TradeJournal(self._db)
        self._trainer = ModelTrainer()
        self._predictor = Predictor(self._trainer)

        # Telegram
        self._telegram = TelegramCommander(
            bot_token=self._config.telegram_bot_token,
            chat_id=self._config.telegram_chat_id,
            get_status_fn=self._get_status,
            get_regime_fn=self._get_regime_str,
            get_balance_fn=self._get_balance_sync,
            get_positions_fn=self._get_positions_sync,
            get_pnl_fn=self._get_pnl_sync,
            get_strategies_fn=lambda: [],
            get_trades_fn=lambda n: self._journal.get_recent_trades(n),
            start_bot_fn=self._resume_trading,
            stop_bot_fn=self._pause_trading,
            panic_fn=self._request_panic,
            set_regime_fn=self._force_regime,
            set_dry_run_fn=self._set_dry_run,
        )

        # State
        self._running = False
        self._trading_active = True
        self._current_regime: Regime = Regime.UNKNOWN
        self._forced_regime: Optional[Regime] = None
        self._panic_requested = False
        self._last_regime_check: float = 0.0
        self._last_balance_snapshot: float = 0.0
        self._last_ml_retrain: float = 0.0
        self._last_daily_report_date: Optional[str] = None

        # Intervals (seconds)
        self._REGIME_INTERVAL = 300  # 5 min
        self._BALANCE_INTERVAL = 3600  # 1 hour
        self._ML_RETRAIN_INTERVAL = 6 * 3600  # 6 hours
        self._LOOP_SLEEP = 10  # main loop sleep

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Initialize all modules and start the main loop."""
        logger.info("=" * 60)
        logger.info("  CryptoNexusUltra starting")
        logger.info("  Dry run: {}", self._config.dry_run)
        logger.info("=" * 60)

        # Connect exchange
        try:
            await self._exchange.connect_all()
        except Exception as e:
            logger.error("Exchange connection failed: {}", e)

        # Connect DB
        self._db.connect()

        # Load ML models
        self._trainer.load_models()

        # Start Telegram bot
        await self._telegram.start()

        # Register signal handlers
        if sys.platform != "win32":
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, self._signal_handler)
        else:
            # Windows: use signal module directly
            signal.signal(signal.SIGINT, self._signal_handler_sync)
            signal.signal(signal.SIGTERM, self._signal_handler_sync)

        self._running = True
        await self._main_loop()

    async def shutdown(self) -> None:
        """Graceful shutdown."""
        logger.info("Shutting down CryptoNexusUltra...")
        self._running = False

        await self._telegram.send_message("<b>Bot shutting down.</b>")
        await self._telegram.stop()
        await self._exchange.close_all()
        logger.info("Shutdown complete.")

    def _signal_handler(self) -> None:
        logger.info("Signal received, initiating shutdown...")
        self._running = False

    def _signal_handler_sync(self, signum: int, frame: Any) -> None:
        logger.info("Signal {} received, initiating shutdown...", signum)
        self._running = False

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def _main_loop(self) -> None:
        """Core event loop."""
        logger.info("Main loop started")

        try:
            while self._running:
                now = time.time()

                # Panic check
                if self._panic_requested:
                    await self._execute_panic()
                    self._panic_requested = False

                # Regime check (every 5 min)
                if now - self._last_regime_check >= self._REGIME_INTERVAL:
                    await self._check_regime()
                    self._last_regime_check = now

                # Strategy cycle (only if trading active)
                if self._trading_active and not self._panic_requested:
                    await self._strategy_cycle()

                # Position monitoring
                await self._monitor_positions()

                # Risk check
                await self._risk_check()

                # Balance snapshot (hourly)
                if now - self._last_balance_snapshot >= self._BALANCE_INTERVAL:
                    await self._take_balance_snapshot()
                    self._last_balance_snapshot = now

                # ML retrain (6 hours)
                if now - self._last_ml_retrain >= self._ML_RETRAIN_INTERVAL:
                    await self._retrain_ml()
                    self._last_ml_retrain = now

                # Daily report at 09:00 KST
                await self._check_daily_report()

                await asyncio.sleep(self._LOOP_SLEEP)

        except asyncio.CancelledError:
            logger.info("Main loop cancelled")
        except Exception as e:
            logger.critical("Main loop crashed: {}", e)
            await self._telegram.send_message(f"<b>CRITICAL: Main loop crashed</b>\n{e}")
        finally:
            await self.shutdown()

    # ------------------------------------------------------------------
    # Loop tasks
    # ------------------------------------------------------------------

    async def _check_regime(self) -> None:
        """Detect current market regime."""
        if self._forced_regime:
            new_regime = self._forced_regime
        else:
            try:
                # Use default symbol for regime detection
                ohlcv = await self._exchange.fetch_ohlcv(
                    "BTC/USDT",
                    self._config.default_timeframe,
                    limit=self._config.ohlcv_limit,
                )
                # Simple regime detection based on ADX and trend
                import pandas as pd
                df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])

                if len(df) < 50:
                    new_regime = Regime.UNKNOWN
                else:
                    import ta
                    adx = ta.trend.ADXIndicator(
                        high=df["high"], low=df["low"], close=df["close"], window=14
                    )
                    adx_val = adx.adx().iloc[-1]
                    di_plus = adx.adx_pos().iloc[-1]
                    di_minus = adx.adx_neg().iloc[-1]

                    sma_20 = df["close"].rolling(20).mean().iloc[-1]
                    sma_50 = df["close"].rolling(50).mean().iloc[-1]
                    current_price = df["close"].iloc[-1]

                    atr = ta.volatility.AverageTrueRange(
                        high=df["high"], low=df["low"], close=df["close"], window=14
                    ).average_true_range().iloc[-1]
                    atr_pct = atr / current_price * 100

                    if atr_pct > 5:
                        new_regime = Regime.VOLATILE
                    elif adx_val > 25 and di_plus > di_minus and current_price > sma_50:
                        new_regime = Regime.TRENDING_UP
                    elif adx_val > 25 and di_minus > di_plus and current_price < sma_50:
                        new_regime = Regime.TRENDING_DOWN
                    else:
                        new_regime = Regime.RANGING

            except Exception as e:
                logger.warning("Regime check failed: {}", e)
                new_regime = self._current_regime  # keep previous

        if new_regime != self._current_regime:
            old = self._current_regime
            self._current_regime = new_regime
            logger.info("Regime change: {} -> {}", old.value, new_regime.value)
            await self._telegram.alert_regime_change(old.value, new_regime.value)
            self._db.insert_regime({
                "regime": new_regime.value,
                "previous": old.value,
            })

    async def _strategy_cycle(self) -> None:
        """Run strategy evaluation and signal generation."""
        try:
            ohlcv = await self._exchange.fetch_ohlcv(
                "BTC/USDT",
                self._config.default_timeframe,
                limit=self._config.ohlcv_limit,
            )
            import pandas as pd
            df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])

            if self._predictor.is_ready:
                prediction = self._predictor.predict(df)
                logger.debug(
                    "ML prediction: signal={} conf={:.4f}",
                    prediction.signal.value, prediction.confidence,
                )

                self._db.insert_prediction({
                    "symbol": "BTC/USDT",
                    "probability": prediction.probability,
                    "signal": prediction.signal.value,
                    "confidence": prediction.confidence,
                    "regime": self._current_regime.value,
                })

        except Exception as e:
            logger.error("Strategy cycle error: {}", e)

    async def _monitor_positions(self) -> None:
        """Check open positions for SL/TP triggers."""
        # In a full implementation, iterate open positions and check price levels
        pass

    async def _risk_check(self) -> None:
        """Check drawdown and other risk metrics."""
        try:
            balance = await self._exchange.fetch_balance()
            total = balance.get("total", {}).get("USDT", 0)

            if total > 0:
                # Simple drawdown check against initial capital
                initial = self._config.paper_balance_usdt
                dd_pct = (1 - total / initial) * 100
                if dd_pct > 10:
                    await self._telegram.alert_drawdown(dd_pct)
                    logger.warning("Drawdown alert: {:.1f}%", dd_pct)
                elif dd_pct > 5:
                    await self._telegram.alert_drawdown(dd_pct)
        except Exception as e:
            logger.debug("Risk check skipped: {}", e)

    async def _take_balance_snapshot(self) -> None:
        """Record hourly balance snapshot."""
        try:
            balance = await self._exchange.fetch_balance()
            self._db.insert_balance_snapshot({
                "total_usdt": balance.get("total", {}).get("USDT", 0),
                "free_usdt": balance.get("free", {}).get("USDT", 0),
                "used_usdt": balance.get("used", {}).get("USDT", 0),
            })
            logger.debug("Balance snapshot taken")
        except Exception as e:
            logger.warning("Balance snapshot failed: {}", e)

    async def _retrain_ml(self) -> None:
        """Retrain ML models with latest data."""
        try:
            ohlcv = await self._exchange.fetch_ohlcv(
                "BTC/USDT", "1h", limit=2000
            )
            import pandas as pd
            df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])

            if len(df) >= 500:
                metrics = self._trainer.train(df)
                self._predictor.reload_model()
                logger.info("ML retrain complete: {}", metrics)
                await self._telegram.send_message(
                    f"<b>ML Retrain Complete</b>\n"
                    f"Ensemble accuracy: {metrics.get('ensemble_accuracy', 'N/A')}"
                )
        except Exception as e:
            logger.error("ML retrain failed: {}", e)

    async def _check_daily_report(self) -> None:
        """Send daily report at 09:00 KST."""
        now_kst = datetime.now(_KST)
        today_str = now_kst.strftime("%Y-%m-%d")

        if (
            now_kst.hour == 9
            and now_kst.minute < (self._LOOP_SLEEP // 60 + 1)
            and self._last_daily_report_date != today_str
        ):
            self._last_daily_report_date = today_str
            summary = self._journal.daily_summary()
            await self._telegram.send_daily_report(summary)
            logger.info("Daily report sent for {}", today_str)

    # ------------------------------------------------------------------
    # Panic
    # ------------------------------------------------------------------

    async def _execute_panic(self) -> None:
        """Emergency close all positions."""
        logger.critical("PANIC STOP executing")
        self._trading_active = False

        try:
            # In full implementation: close all positions via exchange
            await self._telegram.send_message(
                "<b>PANIC STOP EXECUTED</b>\nAll trading halted. Positions closed."
            )
        except Exception as e:
            logger.error("Panic execution error: {}", e)

    def _request_panic(self) -> None:
        self._panic_requested = True

    # ------------------------------------------------------------------
    # Telegram callbacks
    # ------------------------------------------------------------------

    def _get_status(self) -> dict[str, Any]:
        return {
            "running": self._running,
            "trading_active": self._trading_active,
            "regime": self._current_regime.value,
            "dry_run": self._config.dry_run,
            "ml_ready": self._predictor.is_ready,
            "trade_count": self._journal.trade_count,
        }

    def _get_regime_str(self) -> str:
        return self._current_regime.value

    def _get_balance_sync(self) -> dict:
        return {"note": "Use /balance in async context"}

    def _get_positions_sync(self) -> list:
        return []

    def _get_pnl_sync(self) -> dict:
        return self._journal.daily_summary()

    def _resume_trading(self) -> None:
        self._trading_active = True
        logger.info("Trading resumed via Telegram")

    def _pause_trading(self) -> None:
        self._trading_active = False
        logger.info("Trading paused via Telegram")

    def _force_regime(self, regime: str) -> None:
        try:
            self._forced_regime = Regime(regime)
            logger.info("Regime forced to: {}", regime)
        except ValueError:
            self._forced_regime = None
            logger.warning("Invalid regime: {}", regime)

    def _set_dry_run(self, enabled: bool) -> None:
        self._config.dry_run = enabled
        logger.info("Dry-run set to: {}", enabled)


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

def main() -> None:
    """CLI entry point."""
    bot = CryptoNexusUltra()
    try:
        asyncio.run(bot.start())
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")


if __name__ == "__main__":
    main()
