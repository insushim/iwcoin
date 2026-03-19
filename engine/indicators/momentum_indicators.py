"""Momentum indicators using pandas and the ta library."""

import pandas as pd
import numpy as np
import ta


def calc_rsi(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Relative Strength Index."""
    df = df.copy()
    df[f"rsi_{period}"] = ta.momentum.RSIIndicator(
        close=df["close"], window=period
    ).rsi()
    return df


def calc_stochastic(
    df: pd.DataFrame, k_period: int = 14, d_period: int = 3
) -> pd.DataFrame:
    """Stochastic Oscillator (%K and %D)."""
    df = df.copy()
    stoch = ta.momentum.StochasticOscillator(
        high=df["high"],
        low=df["low"],
        close=df["close"],
        window=k_period,
        smooth_window=d_period,
    )
    df["stoch_k"] = stoch.stoch()
    df["stoch_d"] = stoch.stoch_signal()
    return df


def calc_cci(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    """Commodity Channel Index."""
    df = df.copy()
    df[f"cci_{period}"] = ta.trend.CCIIndicator(
        high=df["high"],
        low=df["low"],
        close=df["close"],
        window=period,
    ).cci()
    return df


def calc_williams_r(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Williams %R."""
    df = df.copy()
    df[f"williams_r_{period}"] = ta.momentum.WilliamsRIndicator(
        high=df["high"],
        low=df["low"],
        close=df["close"],
        lbp=period,
    ).williams_r()
    return df


def calc_roc(df: pd.DataFrame, period: int = 12) -> pd.DataFrame:
    """Rate of Change."""
    df = df.copy()
    df[f"roc_{period}"] = ta.momentum.ROCIndicator(
        close=df["close"], window=period
    ).roc()
    return df


def calc_mfi(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Money Flow Index."""
    df = df.copy()
    df[f"mfi_{period}"] = ta.volume.MFIIndicator(
        high=df["high"],
        low=df["low"],
        close=df["close"],
        volume=df["volume"],
        window=period,
    ).money_flow_index()
    return df


def calc_rmi(df: pd.DataFrame, period: int = 14, momentum: int = 5) -> pd.DataFrame:
    """Relative Momentum Index (manual calculation).

    Like RSI but compares close to close N bars ago instead of 1 bar ago.
    """
    df = df.copy()
    delta = df["close"] - df["close"].shift(momentum)
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)

    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()

    # Smooth using exponential moving style after initial window
    for i in range(period + momentum, len(df)):
        avg_gain.iloc[i] = (avg_gain.iloc[i - 1] * (period - 1) + gain.iloc[i]) / period
        avg_loss.iloc[i] = (avg_loss.iloc[i - 1] * (period - 1) + loss.iloc[i]) / period

    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["rmi"] = 100 - (100 / (1 + rs))
    return df
