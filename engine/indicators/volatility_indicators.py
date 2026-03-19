"""Volatility indicators using pandas and the ta library."""

import pandas as pd
import ta


def calc_bollinger_bands(
    df: pd.DataFrame, period: int = 20, std_dev: float = 2.0
) -> pd.DataFrame:
    """Bollinger Bands with width and %B."""
    df = df.copy()
    bb = ta.volatility.BollingerBands(
        close=df["close"], window=period, window_dev=std_dev
    )
    df["bb_upper"] = bb.bollinger_hband()
    df["bb_middle"] = bb.bollinger_mavg()
    df["bb_lower"] = bb.bollinger_lband()
    df["bb_width"] = bb.bollinger_wband()
    df["bb_pctb"] = bb.bollinger_pband()
    return df


def calc_atr(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Average True Range."""
    df = df.copy()
    df[f"atr_{period}"] = ta.volatility.AverageTrueRange(
        high=df["high"], low=df["low"], close=df["close"], window=period
    ).average_true_range()
    return df


def calc_keltner_channel(
    df: pd.DataFrame, ema_period: int = 20, atr_period: int = 10, multiplier: float = 2.0
) -> pd.DataFrame:
    """Keltner Channel."""
    df = df.copy()
    kc = ta.volatility.KeltnerChannel(
        high=df["high"],
        low=df["low"],
        close=df["close"],
        window=ema_period,
        window_atr=atr_period,
        multiplier=multiplier,
    )
    df["kc_upper"] = kc.keltner_channel_hband()
    df["kc_middle"] = kc.keltner_channel_mband()
    df["kc_lower"] = kc.keltner_channel_lband()
    return df


def calc_donchian_channel(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    """Donchian Channel."""
    df = df.copy()
    dc = ta.volatility.DonchianChannel(
        high=df["high"], low=df["low"], close=df["close"], window=period
    )
    df["dc_upper"] = dc.donchian_channel_hband()
    df["dc_middle"] = dc.donchian_channel_mband()
    df["dc_lower"] = dc.donchian_channel_lband()
    return df
