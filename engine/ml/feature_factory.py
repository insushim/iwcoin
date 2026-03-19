"""Feature engineering pipeline for ML models.

Creates 60+ features from OHLCV data covering price action, moving averages,
momentum, volatility, volume, trend, and time-based features.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import ta
from loguru import logger


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_div(a: pd.Series, b: pd.Series) -> pd.Series:
    return a / b.replace(0, np.nan)


# ---------------------------------------------------------------------------
# Feature groups
# ---------------------------------------------------------------------------

def _price_features(df: pd.DataFrame) -> pd.DataFrame:
    """Returns, log-returns, candle anatomy."""
    c = df["close"]
    o = df["open"]
    h = df["high"]
    l = df["low"]

    df["return_1"] = c.pct_change(1)
    df["return_3"] = c.pct_change(3)
    df["return_5"] = c.pct_change(5)
    df["return_10"] = c.pct_change(10)
    df["return_20"] = c.pct_change(20)

    df["log_return_1"] = np.log(c / c.shift(1))
    df["log_return_5"] = np.log(c / c.shift(5))

    candle_range = h - l
    df["upper_shadow"] = _safe_div(h - pd.concat([c, o], axis=1).max(axis=1), candle_range)
    df["lower_shadow"] = _safe_div(pd.concat([c, o], axis=1).min(axis=1) - l, candle_range)
    df["body_ratio"] = _safe_div((c - o).abs(), candle_range)
    df["candle_direction"] = np.sign(c - o)

    return df


def _ma_features(df: pd.DataFrame) -> pd.DataFrame:
    """SMA, EMA, crossovers, alignment score."""
    c = df["close"]

    for p in (7, 20, 50, 100, 200):
        df[f"sma_{p}"] = c.rolling(p).mean()
        df[f"ema_{p}"] = c.ewm(span=p, adjust=False).mean()

    # Distance from MAs (normalized)
    for p in (7, 20, 50, 200):
        df[f"close_vs_sma_{p}"] = _safe_div(c - df[f"sma_{p}"], df[f"sma_{p}"])
        df[f"close_vs_ema_{p}"] = _safe_div(c - df[f"ema_{p}"], df[f"ema_{p}"])

    # Crossovers
    df["sma_7_20_cross"] = (df["sma_7"] > df["sma_20"]).astype(int)
    df["sma_20_50_cross"] = (df["sma_20"] > df["sma_50"]).astype(int)
    df["ema_7_20_cross"] = (df["ema_7"] > df["ema_20"]).astype(int)

    # Alignment score: how many short MAs are above long MAs (0-6)
    pairs = [
        ("sma_7", "sma_20"), ("sma_20", "sma_50"), ("sma_50", "sma_100"),
        ("sma_100", "sma_200"), ("ema_7", "ema_20"), ("ema_20", "ema_50"),
    ]
    alignment = pd.DataFrame(index=df.index)
    for short, long in pairs:
        alignment[f"{short}_{long}"] = (df[short] > df[long]).astype(int)
    df["ma_alignment_score"] = alignment.sum(axis=1)

    return df


def _momentum_features(df: pd.DataFrame) -> pd.DataFrame:
    """RSI, MACD, Stochastic, CCI, Williams %R, ROC."""
    c, h, l, v = df["close"], df["high"], df["low"], df["volume"]

    # RSI
    for p in (7, 14, 21):
        df[f"rsi_{p}"] = ta.momentum.RSIIndicator(close=c, window=p).rsi()

    # MACD
    macd = ta.trend.MACD(close=c, window_slow=26, window_fast=12, window_sign=9)
    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["macd_hist"] = macd.macd_diff()

    # Stochastic
    stoch = ta.momentum.StochasticOscillator(high=h, low=l, close=c, window=14, smooth_window=3)
    df["stoch_k"] = stoch.stoch()
    df["stoch_d"] = stoch.stoch_signal()

    # CCI
    df["cci_20"] = ta.trend.CCIIndicator(high=h, low=l, close=c, window=20).cci()

    # Williams %R
    df["williams_r_14"] = ta.momentum.WilliamsRIndicator(high=h, low=l, close=c, lbp=14).williams_r()

    # ROC
    for p in (6, 12):
        df[f"roc_{p}"] = ta.momentum.ROCIndicator(close=c, window=p).roc()

    # MFI
    df["mfi_14"] = ta.volume.MFIIndicator(high=h, low=l, close=c, volume=v, window=14).money_flow_index()

    return df


def _volatility_features(df: pd.DataFrame) -> pd.DataFrame:
    """Bollinger Bands, ATR, volatility ratios."""
    c, h, l = df["close"], df["high"], df["low"]

    bb = ta.volatility.BollingerBands(close=c, window=20, window_dev=2)
    df["bb_upper"] = bb.bollinger_hband()
    df["bb_lower"] = bb.bollinger_lband()
    df["bb_mid"] = bb.bollinger_mavg()
    df["bb_width"] = _safe_div(df["bb_upper"] - df["bb_lower"], df["bb_mid"])
    df["bb_pct"] = bb.bollinger_pband()

    for p in (7, 14):
        atr = ta.volatility.AverageTrueRange(high=h, low=l, close=c, window=p)
        df[f"atr_{p}"] = atr.average_true_range()
        df[f"atr_{p}_pct"] = _safe_div(df[f"atr_{p}"], c)

    # Realized volatility ratio (short / long)
    df["vol_ratio_7_21"] = _safe_div(
        df["log_return_1"].rolling(7).std(),
        df["log_return_1"].rolling(21).std(),
    )

    return df


def _volume_features(df: pd.DataFrame) -> pd.DataFrame:
    """Volume ratio, OBV, MFI (already in momentum)."""
    v = df["volume"]

    for p in (5, 10, 20):
        df[f"vol_ratio_{p}"] = _safe_div(v, v.rolling(p).mean())

    df["obv"] = ta.volume.OnBalanceVolumeIndicator(close=df["close"], volume=v).on_balance_volume()
    df["obv_slope_5"] = df["obv"].diff(5)

    return df


def _trend_features(df: pd.DataFrame) -> pd.DataFrame:
    """ADX, DI+, DI-, SuperTrend proxy."""
    h, l, c = df["high"], df["low"], df["close"]

    adx_ind = ta.trend.ADXIndicator(high=h, low=l, close=c, window=14)
    df["adx_14"] = adx_ind.adx()
    df["di_plus_14"] = adx_ind.adx_pos()
    df["di_minus_14"] = adx_ind.adx_neg()
    df["di_diff"] = df["di_plus_14"] - df["di_minus_14"]

    # SuperTrend proxy (ATR-based)
    atr = df["atr_14"] if "atr_14" in df.columns else ta.volatility.AverageTrueRange(
        high=h, low=l, close=c, window=14
    ).average_true_range()
    hl2 = (h + l) / 2
    df["supertrend_upper"] = hl2 + 3 * atr
    df["supertrend_lower"] = hl2 - 3 * atr
    df["supertrend_dir"] = np.where(c > df["supertrend_upper"].shift(1), 1,
                            np.where(c < df["supertrend_lower"].shift(1), -1, 0))

    return df


def _time_features(df: pd.DataFrame) -> pd.DataFrame:
    """Sin/cos encoding of hour-of-day and day-of-week."""
    if "timestamp" in df.columns:
        ts = pd.to_datetime(df["timestamp"])
    elif isinstance(df.index, pd.DatetimeIndex):
        ts = df.index
    else:
        return df

    hour = ts.hour + ts.minute / 60.0
    dow = ts.dayofweek

    df["hour_sin"] = np.sin(2 * np.pi * hour / 24)
    df["hour_cos"] = np.cos(2 * np.pi * hour / 24)
    df["dow_sin"] = np.sin(2 * np.pi * dow / 7)
    df["dow_cos"] = np.cos(2 * np.pi * dow / 7)

    return df


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def create_features(
    df: pd.DataFrame,
    target_periods: int = 5,
    include_target: bool = True,
) -> pd.DataFrame:
    """Create 60+ features from OHLCV DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        Must have columns: open, high, low, close, volume.
        Optionally: timestamp (or DatetimeIndex).
    target_periods : int
        Number of future candles for target direction label.
    include_target : bool
        If True, add 'target' column (1=up, 0=down).

    Returns
    -------
    pd.DataFrame
        Original columns + all generated features. NaN rows NOT dropped
        (caller decides how to handle).
    """
    required = {"open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns: {missing}")

    df = df.copy()
    logger.debug("Creating features for {} rows", len(df))

    df = _price_features(df)
    df = _ma_features(df)
    df = _momentum_features(df)
    df = _volatility_features(df)
    df = _volume_features(df)
    df = _trend_features(df)
    df = _time_features(df)

    if include_target:
        future_return = df["close"].shift(-target_periods) / df["close"] - 1
        df["target"] = (future_return > 0).astype(int)

    feature_cols = [c for c in df.columns if c not in ("open", "high", "low", "close", "volume", "timestamp", "target")]
    logger.info("Created {} features", len(feature_cols))
    return df
