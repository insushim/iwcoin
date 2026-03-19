"""Loguru logger setup with file rotation and telegram-ready formatting."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from loguru import logger

_configured = False


def setup_logger(
    level: str = "INFO",
    log_dir: str = "logs",
    rotation: str = "50 MB",
    retention: str = "30 days",
    compression: str = "gz",
) -> None:
    """Configure loguru sinks. Safe to call multiple times (idempotent)."""
    global _configured
    if _configured:
        return
    _configured = True

    logger.remove()  # remove default stderr sink

    fmt = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )

    # Console
    logger.add(sys.stderr, format=fmt, level=level, colorize=True)

    # File – all levels
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    logger.add(
        str(log_path / "bot_{time:YYYY-MM-DD}.log"),
        format=fmt,
        level="DEBUG",
        rotation=rotation,
        retention=retention,
        compression=compression,
        encoding="utf-8",
    )

    # Error-only file
    logger.add(
        str(log_path / "error_{time:YYYY-MM-DD}.log"),
        format=fmt,
        level="ERROR",
        rotation=rotation,
        retention=retention,
        compression=compression,
        encoding="utf-8",
    )


def format_telegram(
    level: str,
    message: str,
    extra: Optional[dict] = None,
) -> str:
    """Format a log message for Telegram (HTML parse mode)."""
    icon = {
        "DEBUG": "🔍",
        "INFO": "ℹ️",
        "WARNING": "⚠️",
        "ERROR": "❌",
        "CRITICAL": "🔥",
    }.get(level.upper(), "📝")

    lines = [f"{icon} <b>[{level.upper()}]</b>", message]
    if extra:
        for k, v in extra.items():
            lines.append(f"  <code>{k}</code>: {v}")
    return "\n".join(lines)
