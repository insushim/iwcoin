"""Volume indicators using pandas and the ta library."""

import pandas as pd
import numpy as np
import ta


def calc_obv(df: pd.DataFrame) -> pd.DataFrame:
    """On-Balance Volume."""
    df = df.copy()
    df["obv"] = ta.volume.OnBalanceVolumeIndicator(
        close=df["close"], volume=df["volume"]
    ).on_balance_volume()
    return df


def calc_vwap(df: pd.DataFrame) -> pd.DataFrame:
    """Volume Weighted Average Price.

    Calculates cumulative VWAP over the entire DataFrame.
    For intraday reset-by-session, pre-group your data.
    """
    df = df.copy()
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    cum_tp_vol = (typical_price * df["volume"]).cumsum()
    cum_vol = df["volume"].cumsum()
    df["vwap"] = cum_tp_vol / cum_vol.replace(0, np.nan)
    return df


def calc_cmf(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    """Chaikin Money Flow."""
    df = df.copy()
    df[f"cmf_{period}"] = ta.volume.ChaikinMoneyFlowIndicator(
        high=df["high"],
        low=df["low"],
        close=df["close"],
        volume=df["volume"],
        window=period,
    ).chaikin_money_flow()
    return df


def calc_volume_profile(
    df: pd.DataFrame, bins: int = 50, lookback: int | None = None
) -> pd.DataFrame:
    """Volume Profile — volume distributed across price bins.

    Adds columns:
      vp_poc   - Point of Control (price level with highest volume)
      vp_vah   - Value Area High (upper bound of 70% volume)
      vp_val   - Value Area Low  (lower bound of 70% volume)
    """
    df = df.copy()
    subset = df if lookback is None else df.tail(lookback)

    if len(subset) < 2:
        df["vp_poc"] = np.nan
        df["vp_vah"] = np.nan
        df["vp_val"] = np.nan
        return df

    price_min = subset["low"].min()
    price_max = subset["high"].max()
    if price_min == price_max:
        df["vp_poc"] = price_min
        df["vp_vah"] = price_max
        df["vp_val"] = price_min
        return df

    bin_edges = np.linspace(price_min, price_max, bins + 1)
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
    vol_per_bin = np.zeros(bins)

    for _, row in subset.iterrows():
        # Distribute each bar's volume across bins it spans
        mask = (bin_centers >= row["low"]) & (bin_centers <= row["high"])
        touched = mask.sum()
        if touched > 0:
            vol_per_bin[mask] += row["volume"] / touched

    poc_idx = int(np.argmax(vol_per_bin))
    poc_price = float(bin_centers[poc_idx])

    # Value area: 70% of total volume centered around POC
    total_vol = vol_per_bin.sum()
    target = total_vol * 0.70
    lo, hi = poc_idx, poc_idx
    area_vol = vol_per_bin[poc_idx]
    while area_vol < target and (lo > 0 or hi < bins - 1):
        expand_lo = vol_per_bin[lo - 1] if lo > 0 else 0
        expand_hi = vol_per_bin[hi + 1] if hi < bins - 1 else 0
        if expand_lo >= expand_hi and lo > 0:
            lo -= 1
            area_vol += vol_per_bin[lo]
        elif hi < bins - 1:
            hi += 1
            area_vol += vol_per_bin[hi]
        else:
            lo -= 1
            area_vol += vol_per_bin[lo]

    df["vp_poc"] = poc_price
    df["vp_vah"] = float(bin_centers[hi])
    df["vp_val"] = float(bin_centers[lo])
    return df
