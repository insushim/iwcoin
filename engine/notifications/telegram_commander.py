"""Telegram bot with command interface and automated alerts."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Any, Callable, Optional

from loguru import logger

try:
    from telegram import Update, Bot
    from telegram.ext import (
        Application,
        CommandHandler,
        ContextTypes,
    )

    _TELEGRAM_AVAILABLE = True
except ImportError:
    _TELEGRAM_AVAILABLE = False
    Update = Any  # type: ignore[assignment, misc]
    ContextTypes = Any  # type: ignore[assignment, misc]


# KST = UTC + 9
_KST = timezone(timedelta(hours=9))


class TelegramCommander:
    """Full-featured Telegram command interface and alert system.

    Commands:
        /start, /help        - Welcome / command list
        /status              - Bot status overview
        /regime              - Current market regime
        /balance             - Account balance
        /positions           - Open positions
        /pnl                 - Today's PnL summary
        /strategies          - Strategy performance
        /trades [n]          - Recent N trades
        /start_bot           - Start trading
        /stop_bot            - Stop trading
        /panic               - Emergency close all
        /set_regime <regime> - Force regime override
        /dry_run <on|off>    - Toggle dry-run mode

    Auto-alerts:
        - New trade executed
        - Stop loss triggered
        - Regime change detected
        - Drawdown warning (>5%, >10%)
        - Daily report at 09:00 KST
    """

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        get_status_fn: Optional[Callable[[], dict]] = None,
        get_regime_fn: Optional[Callable[[], str]] = None,
        get_balance_fn: Optional[Callable[[], dict]] = None,
        get_positions_fn: Optional[Callable[[], list]] = None,
        get_pnl_fn: Optional[Callable[[], dict]] = None,
        get_strategies_fn: Optional[Callable[[], list]] = None,
        get_trades_fn: Optional[Callable[[int], list]] = None,
        start_bot_fn: Optional[Callable[[], None]] = None,
        stop_bot_fn: Optional[Callable[[], None]] = None,
        panic_fn: Optional[Callable[[], None]] = None,
        set_regime_fn: Optional[Callable[[str], None]] = None,
        set_dry_run_fn: Optional[Callable[[bool], None]] = None,
    ) -> None:
        if not _TELEGRAM_AVAILABLE:
            logger.warning("python-telegram-bot not installed. Telegram features disabled.")

        self._token = bot_token
        self._chat_id = chat_id
        self._app: Optional[Any] = None
        self._bot: Optional[Any] = None

        # Callback bindings
        self._get_status = get_status_fn or (lambda: {"status": "unknown"})
        self._get_regime = get_regime_fn or (lambda: "unknown")
        self._get_balance = get_balance_fn or (lambda: {})
        self._get_positions = get_positions_fn or (lambda: [])
        self._get_pnl = get_pnl_fn or (lambda: {})
        self._get_strategies = get_strategies_fn or (lambda: [])
        self._get_trades = get_trades_fn or (lambda n: [])
        self._start_bot = start_bot_fn
        self._stop_bot = stop_bot_fn
        self._panic = panic_fn
        self._set_regime = set_regime_fn
        self._set_dry_run = set_dry_run_fn

        self._authorized_chat_id = str(chat_id) if chat_id else ""

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Initialize and start the Telegram bot polling."""
        if not _TELEGRAM_AVAILABLE or not self._token:
            logger.warning("Telegram bot not started (missing token or library)")
            return

        self._app = Application.builder().token(self._token).build()
        self._bot = self._app.bot

        handlers = [
            ("start", self._cmd_start),
            ("help", self._cmd_help),
            ("status", self._cmd_status),
            ("regime", self._cmd_regime),
            ("balance", self._cmd_balance),
            ("positions", self._cmd_positions),
            ("pnl", self._cmd_pnl),
            ("strategies", self._cmd_strategies),
            ("trades", self._cmd_trades),
            ("start_bot", self._cmd_start_bot),
            ("stop_bot", self._cmd_stop_bot),
            ("panic", self._cmd_panic),
            ("set_regime", self._cmd_set_regime),
            ("dry_run", self._cmd_dry_run),
        ]
        for name, handler in handlers:
            self._app.add_handler(CommandHandler(name, handler))

        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(drop_pending_updates=True)
        logger.info("Telegram bot started")

    async def stop(self) -> None:
        """Gracefully stop the bot."""
        if self._app:
            try:
                await self._app.updater.stop()
                await self._app.stop()
                await self._app.shutdown()
            except Exception as e:
                logger.warning("Error stopping Telegram bot: {}", e)

    # ------------------------------------------------------------------
    # Auth check
    # ------------------------------------------------------------------

    def _is_authorized(self, update: Any) -> bool:
        if not self._authorized_chat_id:
            return True
        return str(update.effective_chat.id) == self._authorized_chat_id

    async def _unauthorized(self, update: Any) -> None:
        await update.message.reply_text("Unauthorized.")

    # ------------------------------------------------------------------
    # Command handlers
    # ------------------------------------------------------------------

    async def _cmd_start(self, update: Any, context: Any) -> None:
        if not self._is_authorized(update):
            return await self._unauthorized(update)
        await update.message.reply_html(
            "<b>CryptoNexusUltra Bot</b>\n\n"
            "Use /help to see available commands."
        )

    async def _cmd_help(self, update: Any, context: Any) -> None:
        if not self._is_authorized(update):
            return await self._unauthorized(update)
        text = (
            "<b>Commands:</b>\n"
            "/status - Bot status\n"
            "/regime - Market regime\n"
            "/balance - Account balance\n"
            "/positions - Open positions\n"
            "/pnl - Today's PnL\n"
            "/strategies - Strategy performance\n"
            "/trades [n] - Recent trades\n"
            "/start_bot - Start trading\n"
            "/stop_bot - Stop trading\n"
            "/panic - Emergency close all\n"
            "/set_regime &lt;regime&gt; - Force regime\n"
            "/dry_run &lt;on|off&gt; - Toggle dry-run\n"
        )
        await update.message.reply_html(text)

    async def _cmd_status(self, update: Any, context: Any) -> None:
        if not self._is_authorized(update):
            return await self._unauthorized(update)
        status = self._get_status()
        lines = [f"<b>{k}:</b> {v}" for k, v in status.items()]
        await update.message.reply_html("\n".join(lines) or "No status available.")

    async def _cmd_regime(self, update: Any, context: Any) -> None:
        if not self._is_authorized(update):
            return await self._unauthorized(update)
        regime = self._get_regime()
        await update.message.reply_html(f"<b>Current Regime:</b> {regime}")

    async def _cmd_balance(self, update: Any, context: Any) -> None:
        if not self._is_authorized(update):
            return await self._unauthorized(update)
        bal = self._get_balance()
        lines = [f"<code>{k}</code>: {v}" for k, v in bal.items()]
        await update.message.reply_html("\n".join(lines) or "No balance data.")

    async def _cmd_positions(self, update: Any, context: Any) -> None:
        if not self._is_authorized(update):
            return await self._unauthorized(update)
        positions = self._get_positions()
        if not positions:
            await update.message.reply_text("No open positions.")
            return
        lines = []
        for p in positions:
            lines.append(
                f"  {p.get('symbol', '?')} {p.get('side', '?')} "
                f"size={p.get('size', 0)} entry={p.get('entry_price', 0)}"
            )
        await update.message.reply_html("<b>Open Positions:</b>\n" + "\n".join(lines))

    async def _cmd_pnl(self, update: Any, context: Any) -> None:
        if not self._is_authorized(update):
            return await self._unauthorized(update)
        pnl = self._get_pnl()
        lines = [f"<b>{k}:</b> {v}" for k, v in pnl.items()]
        await update.message.reply_html("\n".join(lines) or "No PnL data.")

    async def _cmd_strategies(self, update: Any, context: Any) -> None:
        if not self._is_authorized(update):
            return await self._unauthorized(update)
        strategies = self._get_strategies()
        if not strategies:
            await update.message.reply_text("No strategy data.")
            return
        lines = []
        for s in strategies:
            lines.append(f"  {s.get('name', '?')}: score={s.get('score', 0)}")
        await update.message.reply_html("<b>Strategies:</b>\n" + "\n".join(lines))

    async def _cmd_trades(self, update: Any, context: Any) -> None:
        if not self._is_authorized(update):
            return await self._unauthorized(update)
        n = 10
        if context.args:
            try:
                n = int(context.args[0])
            except ValueError:
                pass
        trades = self._get_trades(n)
        if not trades:
            await update.message.reply_text("No recent trades.")
            return
        lines = []
        for t in trades[-n:]:
            lines.append(
                f"  {t.get('side', '?')} {t.get('symbol', '?')} "
                f"pnl={t.get('pnl', 0):.2f}"
            )
        await update.message.reply_html("<b>Recent Trades:</b>\n" + "\n".join(lines))

    async def _cmd_start_bot(self, update: Any, context: Any) -> None:
        if not self._is_authorized(update):
            return await self._unauthorized(update)
        if self._start_bot:
            self._start_bot()
            await update.message.reply_text("Bot started.")
        else:
            await update.message.reply_text("Start function not configured.")

    async def _cmd_stop_bot(self, update: Any, context: Any) -> None:
        if not self._is_authorized(update):
            return await self._unauthorized(update)
        if self._stop_bot:
            self._stop_bot()
            await update.message.reply_text("Bot stopped.")
        else:
            await update.message.reply_text("Stop function not configured.")

    async def _cmd_panic(self, update: Any, context: Any) -> None:
        if not self._is_authorized(update):
            return await self._unauthorized(update)
        if self._panic:
            self._panic()
            await update.message.reply_html("<b>PANIC STOP executed. All positions closed.</b>")
        else:
            await update.message.reply_text("Panic function not configured.")

    async def _cmd_set_regime(self, update: Any, context: Any) -> None:
        if not self._is_authorized(update):
            return await self._unauthorized(update)
        if not context.args:
            await update.message.reply_text("Usage: /set_regime <regime_name>")
            return
        regime = context.args[0]
        if self._set_regime:
            self._set_regime(regime)
            await update.message.reply_html(f"Regime set to: <b>{regime}</b>")
        else:
            await update.message.reply_text("Set regime function not configured.")

    async def _cmd_dry_run(self, update: Any, context: Any) -> None:
        if not self._is_authorized(update):
            return await self._unauthorized(update)
        if not context.args:
            await update.message.reply_text("Usage: /dry_run <on|off>")
            return
        val = context.args[0].lower()
        enabled = val in ("on", "true", "1", "yes")
        if self._set_dry_run:
            self._set_dry_run(enabled)
            await update.message.reply_html(f"Dry-run: <b>{'ON' if enabled else 'OFF'}</b>")
        else:
            await update.message.reply_text("Dry-run function not configured.")

    # ------------------------------------------------------------------
    # Alert / notification methods
    # ------------------------------------------------------------------

    async def send_message(self, text: str, parse_mode: str = "HTML") -> None:
        """Send a message to the configured chat."""
        if not self._bot or not self._chat_id:
            logger.debug("Telegram send skipped (not configured)")
            return
        try:
            await self._bot.send_message(
                chat_id=self._chat_id, text=text, parse_mode=parse_mode
            )
        except Exception as e:
            logger.error("Telegram send failed: {}", e)

    async def alert_trade(self, trade: dict[str, Any]) -> None:
        """Alert when a trade is executed."""
        side = trade.get("side", "?").upper()
        symbol = trade.get("symbol", "?")
        pnl = trade.get("pnl", 0)
        strategy = trade.get("strategy", "?")
        text = (
            f"<b>Trade Executed</b>\n"
            f"{side} {symbol}\n"
            f"PnL: <code>{pnl:+.2f}</code>\n"
            f"Strategy: {strategy}"
        )
        await self.send_message(text)

    async def alert_stop_loss(self, symbol: str, loss: float) -> None:
        await self.send_message(
            f"<b>Stop Loss Triggered</b>\n"
            f"Symbol: {symbol}\n"
            f"Loss: <code>{loss:+.2f}</code>"
        )

    async def alert_regime_change(self, old_regime: str, new_regime: str) -> None:
        await self.send_message(
            f"<b>Regime Change</b>\n"
            f"{old_regime} -> <b>{new_regime}</b>"
        )

    async def alert_drawdown(self, drawdown_pct: float) -> None:
        level = "CRITICAL" if drawdown_pct > 10 else "WARNING"
        await self.send_message(
            f"<b>Drawdown {level}</b>\n"
            f"Current drawdown: <code>{drawdown_pct:.1f}%</code>"
        )

    async def send_daily_report(self, report: dict[str, Any]) -> None:
        """Send the 09:00 KST daily report."""
        now_kst = datetime.now(_KST).strftime("%Y-%m-%d %H:%M KST")
        lines = [
            f"<b>Daily Report</b> ({now_kst})\n",
        ]
        for k, v in report.items():
            if isinstance(v, float):
                lines.append(f"  {k}: <code>{v:.2f}</code>")
            else:
                lines.append(f"  {k}: {v}")
        await self.send_message("\n".join(lines))

    # ------------------------------------------------------------------
    # Daily report scheduler helper
    # ------------------------------------------------------------------

    async def schedule_daily_report(
        self,
        report_fn: Callable[[], dict[str, Any]],
        hour: int = 9,
        minute: int = 0,
    ) -> None:
        """Run forever, sending daily report at the specified KST time."""
        while True:
            now = datetime.now(_KST)
            target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if now >= target:
                target += timedelta(days=1)
            wait_sec = (target - now).total_seconds()
            logger.debug("Next daily report in {:.0f}s", wait_sec)
            await asyncio.sleep(wait_sec)

            try:
                report = report_fn()
                await self.send_daily_report(report)
            except Exception as e:
                logger.error("Daily report failed: {}", e)
