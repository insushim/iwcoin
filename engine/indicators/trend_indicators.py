"""Trend indicators using pandas and the ta library."""

import pandas as pd
import numpy as np
import ta


def calc_sma(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    """Simple Moving Average."""
    df = df.copy()
    df[f"sma_{period}"] = ta.trend.SMAIndicator(
        close=df["close"], window=period
    ).sma_indicator()
    return df


def calc_ema(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    """Exponential Moving Average."""
    df = df.copy()
    df[f"ema_{period}"] = ta.trend.EMAIndicator(
        close=df["close"], window=period
    ).ema_indicator()
    return df


def calc_macd(
    df: pd.DataFrame,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.DataFrame:
    """MACD line, signal line, and histogram."""
    df = df.copy()
    macd = ta.trend.MACD(
        close=df["close"],
        window_fast=fast,
        window_slow=slow,
        window_sign=signal,
    )
    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["macd_hist"] = macd.macd_diff()
    return df


def calc_adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Average Directional Index with +DI / -DI."""
    df = df.copy()
    adx = ta.trend.ADXIndicator(
        high=df["high"],
        low=df["low"],
        close=df["close"],
        window=period,
    )
    df["adx"] = adx.adx()
    df["adx_pos"] = adx.adx_pos()
    df["adx_neg"] = adx.adx_neg()
    return df


def calc_ichimoku(
    df: pd.DataFrame,
    tenkan: int = 9,
    kijun: int = 26,
    senkou_b: int = 52,
) -> pd.DataFrame:
    """Ichimoku Cloud components."""
    df = df.copy()
    ich = ta.trend.IchimokuIndicator(
        high=df["high"],
        low=df["low"],
        window1=tenkan,
        window2=kijun,
        window3=senkou_b,
    )
    df["ichimoku_tenkan"] = ich.ichimoku_conversion_line()
    df["ichimoku_kijun"] = ich.ichimoku_base_line()
    df["ichimoku_senkou_a"] = ich.ichimoku_a()
    df["ichimoku_senkou_b"] = ich.ichimoku_b()
    return df


def calc_supertrend(
    df: pd.DataFrame, period: int = 10, multiplier: float = 3.0
) -> pd.DataFrame:
    """Supertrend indicator (manual calculation)."""
    df = df.copy()
    atr = ta.volatility.AverageTrueRange(
        high=df["high"], low=df["low"], close=df["close"], window=period
    ).average_true_range()

    hl2 = (df["high"] + df["low"]) / 2
    upper_band = hl2 + multiplier * atr
    lower_band = hl2 - multiplier * atr

    supertrend = pd.Series(np.nan, index=df.index)
    direction = pd.Series(1, index=df.index)  # 1 = up (bullish), -1 = down

    for i in range(1, len(df)):
        if pd.isna(atr.iloc[i]):
            continue

        prev_upper = upper_band.iloc[i - 1] if not pd.isna(upper_band.iloc[i - 1]) else upper_band.iloc[i]
        prev_lower = lower_band.iloc[i - 1] if not pd.isna(lower_band.iloc[i - 1]) else lower_band.iloc[i]

        if upper_band.iloc[i] < prev_upper or df["close"].iloc[i - 1] > prev_upper:
            pass  # keep current upper
        else:
            upper_band.iloc[i] = prev_upper

        if lower_band.iloc[i] > prev_lower or df["close"].iloc[i - 1] < prev_lower:
            pass
        else:
            lower_band.iloc[i] = prev_lower

        prev_st = supertrend.iloc[i - 1]

        if pd.isna(prev_st):
            if df["close"].iloc[i] <= upper_band.iloc[i]:
                supertrend.iloc[i] = upper_band.iloc[i]
                direction.iloc[i] = -1
            else:
                supertrend.iloc[i] = lower_band.iloc[i]
                direction.iloc[i] = 1
        elif prev_st == upper_band.iloc[i - 1]:
            if df["close"].iloc[i] <= upper_band.iloc[i]:
                supertrend.iloc[i] = upper_band.iloc[i]
                direction.iloc[i] = -1
            else:
                supertrend.iloc[i] = lower_band.iloc[i]
                direction.iloc[i] = 1
        else:
            if df["close"].iloc[i] >= lower_band.iloc[i]:
                supertrend.iloc[i] = lower_band.iloc[i]
                direction.iloc[i] = 1
            else:
                supertrend.iloc[i] = upper_band.iloc[i]
                direction.iloc[i] = -1

    df["supertrend"] = supertrend
    df["supertrend_direction"] = direction
    return df


def calc_parabolic_sar(
    df: pd.DataFrame, step: float = 0.02, max_step: float = 0.2
) -> pd.DataFrame:
    """Parabolic SAR."""
    df = df.copy()
    psar = ta.trend.PSARIndicator(
        high=df["high"],
        low=df["low"],
        close=df["close"],
        step=step,
        max_step=max_step,
    )
    df["psar"] = psar.psar()
    df["psar_up"] = psar.psar_up()
    df["psar_down"] = psar.psar_down()
    return df
