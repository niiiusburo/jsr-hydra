"""
PURPOSE: Trend indicators for identifying and measuring trend direction and strength.
Includes SMA, EMA, MACD, ADX, and Supertrend indicators.
"""

import numpy as np
import pandas as pd
from typing import Tuple


def sma(series: pd.Series, period: int) -> pd.Series:
    """
    PURPOSE: Calculate Simple Moving Average (SMA).

    Args:
        series: Input price series
        period: Number of periods for the moving average

    Returns:
        pd.Series: SMA values (NaN for initial period-1 rows)
    """
    if period < 1:
        raise ValueError("Period must be >= 1")
    return series.rolling(window=period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    """
    PURPOSE: Calculate Exponential Moving Average (EMA).

    Args:
        series: Input price series
        period: Number of periods for the moving average

    Returns:
        pd.Series: EMA values (NaN for initial rows until enough data)
    """
    if period < 1:
        raise ValueError("Period must be >= 1")
    return series.ewm(span=period, adjust=False).mean()


def macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    PURPOSE: Calculate MACD (Moving Average Convergence Divergence).

    Args:
        close: Close price series
        fast: Fast EMA period (default 12)
        slow: Slow EMA period (default 26)
        signal: Signal line EMA period (default 9)

    Returns:
        Tuple[pd.Series, pd.Series, pd.Series]: (macd_line, signal_line, histogram)
            - macd_line: difference between fast and slow EMA
            - signal_line: EMA of MACD line
            - histogram: MACD line minus signal line
    """
    if fast < 1 or slow < 1 or signal < 1:
        raise ValueError("All periods must be >= 1")
    if fast >= slow:
        raise ValueError("Fast period must be less than slow period")

    ema_fast = ema(close, fast)
    ema_slow = ema(close, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal)
    histogram = macd_line - signal_line

    return macd_line, signal_line, histogram


def adx(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14
) -> pd.Series:
    """
    PURPOSE: Calculate Average Directional Index (ADX) - measures trend strength.

    Args:
        high: High price series
        low: Low price series
        close: Close price series
        period: ADX period (default 14)

    Returns:
        pd.Series: ADX values (0-100, higher = stronger trend)
    """
    if period < 1:
        raise ValueError("Period must be >= 1")

    # Calculate true range
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # Calculate directional movements
    up_move = high - high.shift(1)
    down_move = low.shift(1) - low

    pos_dm = up_move.copy()
    pos_dm[up_move <= 0] = 0
    pos_dm[(down_move > up_move)] = 0

    neg_dm = down_move.copy()
    neg_dm[down_move <= 0] = 0
    neg_dm[(up_move >= down_move)] = 0

    # Smooth with simple moving average first
    tr_smooth = tr.rolling(window=period).sum()
    pos_dm_smooth = pos_dm.rolling(window=period).sum()
    neg_dm_smooth = neg_dm.rolling(window=period).sum()

    # Calculate directional indicators
    pos_di = 100 * pos_dm_smooth / tr_smooth
    neg_di = 100 * neg_dm_smooth / tr_smooth

    # Calculate DX
    di_sum = pos_di + neg_di
    di_sum = di_sum.replace(0, np.nan)
    dx = 100 * (pos_di - neg_di).abs() / di_sum

    # Smooth DX with EMA to get ADX
    adx_values = dx.ewm(span=period, adjust=False).mean()

    return adx_values


def supertrend(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 10,
    multiplier: float = 3.0
) -> pd.Series:
    """
    PURPOSE: Calculate Supertrend indicator - identifies trend reversals.

    Args:
        high: High price series
        low: Low price series
        close: Close price series
        period: ATR period (default 10)
        multiplier: ATR multiplier for bands (default 3.0)

    Returns:
        pd.Series: Supertrend values (positive=uptrend, negative=downtrend)
    """
    if period < 1:
        raise ValueError("Period must be >= 1")
    if multiplier <= 0:
        raise ValueError("Multiplier must be positive")

    # Calculate HL2 (average of high and low)
    hl2 = (high + low) / 2

    # Calculate ATR
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr_values = tr.rolling(window=period).mean()

    # Calculate basic bands
    basic_ub = hl2 + multiplier * atr_values
    basic_lb = hl2 - multiplier * atr_values

    # Calculate final bands
    final_ub = basic_ub.copy()
    final_lb = basic_lb.copy()

    for i in range(1, len(final_ub)):
        final_ub.iloc[i] = min(basic_ub.iloc[i], final_ub.iloc[i-1]) if close.iloc[i-1] > final_ub.iloc[i-1] else basic_ub.iloc[i]
        final_lb.iloc[i] = max(basic_lb.iloc[i], final_lb.iloc[i-1]) if close.iloc[i-1] < final_lb.iloc[i-1] else basic_lb.iloc[i]

    # Determine supertrend
    supertrend_values = pd.Series(index=close.index, dtype='float64')
    trend = pd.Series(index=close.index, dtype='float64')

    for i in range(len(close)):
        if i == 0:
            trend.iloc[i] = 1  # Default to uptrend
            supertrend_values.iloc[i] = final_lb.iloc[i]
        else:
            if close.iloc[i] <= final_ub.iloc[i]:
                trend.iloc[i] = -1
                supertrend_values.iloc[i] = final_ub.iloc[i]
            else:
                trend.iloc[i] = 1
                supertrend_values.iloc[i] = final_lb.iloc[i]

    # Return with sign indicating trend direction
    return supertrend_values * trend
