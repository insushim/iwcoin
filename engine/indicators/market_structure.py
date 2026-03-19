"""Market structure analysis: support/resistance, Fibonacci, candle patterns."""

import pandas as pd
import numpy as np


def detect_support_resistance(
    df: pd.DataFrame, left: int = 5, right: int = 5, max_levels: int = 10
) -> pd.DataFrame:
    """Detect support and resistance using pivot points.

    A pivot high requires `left` higher-highs before and `right` higher-highs after.
    A pivot low requires `left` lower-lows before and `right` lower-lows after.

    Adds columns:
      pivot_high  - True at resistance pivot bars
      pivot_low   - True at support pivot bars
      sr_levels   - list of (price, type) tuples (same value every row for convenience)
    """
    df = df.copy()
    n = len(df)
    pivot_high = pd.Series(False, index=df.index)
    pivot_low = pd.Series(False, index=df.index)

    highs = df["high"].values
    lows = df["low"].values

    for i in range(left, n - right):
        # Check pivot high
        is_ph = True
        for j in range(1, left + 1):
            if highs[i - j] >= highs[i]:
                is_ph = False
                break
        if is_ph:
            for j in range(1, right + 1):
                if highs[i + j] >= highs[i]:
                    is_ph = False
                    break
        pivot_high.iloc[i] = is_ph

        # Check pivot low
        is_pl = True
        for j in range(1, left + 1):
            if lows[i - j] <= lows[i]:
                is_pl = False
                break
        if is_pl:
            for j in range(1, right + 1):
                if lows[i + j] <= lows[i]:
                    is_pl = False
                    break
        pivot_low.iloc[i] = is_pl

    df["pivot_high"] = pivot_high
    df["pivot_low"] = pivot_low

    # Collect levels sorted by recency, capped at max_levels
    levels: list[tuple[float, str]] = []
    for i in range(n - 1, -1, -1):
        if pivot_high.iloc[i]:
            levels.append((float(highs[i]), "resistance"))
        if pivot_low.iloc[i]:
            levels.append((float(lows[i]), "support"))
        if len(levels) >= max_levels:
            break

    df["sr_levels"] = [levels] * n
    return df


def calc_fibonacci_levels(
    df: pd.DataFrame, lookback: int | None = None
) -> pd.DataFrame:
    """Fibonacci retracement levels based on the high-low range.

    Adds columns: fib_0, fib_236, fib_382, fib_500, fib_618, fib_786, fib_1.
    """
    df = df.copy()
    subset = df if lookback is None else df.tail(lookback)

    if len(subset) < 2:
        for lvl in ["0", "236", "382", "500", "618", "786", "1"]:
            df[f"fib_{lvl}"] = np.nan
        return df

    high = subset["high"].max()
    low = subset["low"].min()
    diff = high - low

    ratios = {"0": 0.0, "236": 0.236, "382": 0.382, "500": 0.5, "618": 0.618, "786": 0.786, "1": 1.0}

    # Determine trend: if close ended higher than it started, retracement is top-down
    if subset["close"].iloc[-1] >= subset["close"].iloc[0]:
        # Uptrend retracement: levels measured down from high
        for name, ratio in ratios.items():
            df[f"fib_{name}"] = high - diff * ratio
    else:
        # Downtrend retracement: levels measured up from low
        for name, ratio in ratios.items():
            df[f"fib_{name}"] = low + diff * ratio

    return df


def detect_candle_patterns(df: pd.DataFrame) -> pd.DataFrame:
    """Detect common candlestick patterns.

    Adds boolean columns:
      candle_engulfing_bull, candle_engulfing_bear,
      candle_hammer, candle_doji, candle_morning_star
    """
    df = df.copy()
    o = df["open"].values
    h = df["high"].values
    l = df["low"].values  # noqa: E741
    c = df["close"].values
    n = len(df)

    engulfing_bull = np.zeros(n, dtype=bool)
    engulfing_bear = np.zeros(n, dtype=bool)
    hammer = np.zeros(n, dtype=bool)
    doji = np.zeros(n, dtype=bool)
    morning_star = np.zeros(n, dtype=bool)

    for i in range(n):
        body = abs(c[i] - o[i])
        full_range = h[i] - l[i]

        if full_range == 0:
            doji[i] = True
            continue

        body_ratio = body / full_range

        # Doji: body < 10% of range
        if body_ratio < 0.1:
            doji[i] = True

        # Hammer: small body at top, long lower shadow >= 2x body
        upper_shadow = h[i] - max(o[i], c[i])
        lower_shadow = min(o[i], c[i]) - l[i]
        if body > 0 and lower_shadow >= 2 * body and upper_shadow <= body * 0.5:
            hammer[i] = True

        if i < 1:
            continue

        prev_body = abs(c[i - 1] - o[i - 1])

        # Bullish engulfing
        if (
            c[i - 1] < o[i - 1]  # prev bearish
            and c[i] > o[i]  # current bullish
            and o[i] <= c[i - 1]
            and c[i] >= o[i - 1]
            and body > prev_body
        ):
            engulfing_bull[i] = True

        # Bearish engulfing
        if (
            c[i - 1] > o[i - 1]  # prev bullish
            and c[i] < o[i]  # current bearish
            and o[i] >= c[i - 1]
            and c[i] <= o[i - 1]
            and body > prev_body
        ):
            engulfing_bear[i] = True

        if i < 2:
            continue

        # Morning star: bearish candle, small body (star), bullish candle
        first_bearish = c[i - 2] < o[i - 2]
        star_small = abs(c[i - 1] - o[i - 1]) < abs(c[i - 2] - o[i - 2]) * 0.3
        third_bullish = c[i] > o[i]
        closes_into_first = c[i] > (o[i - 2] + c[i - 2]) / 2

        if first_bearish and star_small and third_bullish and closes_into_first:
            morning_star[i] = True

    df["candle_engulfing_bull"] = engulfing_bull
    df["candle_engulfing_bear"] = engulfing_bear
    df["candle_hammer"] = hammer
    df["candle_doji"] = doji
    df["candle_morning_star"] = morning_star
    return df
