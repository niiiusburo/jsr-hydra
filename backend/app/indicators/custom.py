"""
PURPOSE: Custom indicators for JSR Hydra trading system.
Includes Z-Score, Regime Volatility Ratio, Session Range, and Trend Strength.
"""

import numpy as np
import pandas as pd
from .volatility import atr


def z_score(close: pd.Series, period: int = 20) -> pd.Series:
    """
    PURPOSE: Calculate Z-Score (standard deviation distance from mean).
    Identifies when price is extreme relative to recent history.

    Args:
        close: Close price series
        period: Lookback period for mean and standard deviation (default 20)

    Returns:
        pd.Series: Z-Score values (typically -3 to +3, extremes >2 or <-2)
    """
    if period < 1:
        raise ValueError("Period must be >= 1")

    # Calculate rolling mean and standard deviation
    mean = close.rolling(window=period).mean()
    std = close.rolling(window=period).std()

    # Avoid division by zero
    std = std.replace(0, 1)

    # Calculate Z-Score
    z_score_values = (close - mean) / std

    return z_score_values


def regime_volatility_ratio(
    atr_short: pd.Series,
    atr_long: pd.Series
) -> pd.Series:
    """
    PURPOSE: Calculate ratio of short-term to long-term volatility.
    Identifies volatility expansion or contraction regimes.

    Args:
        atr_short: Short-term ATR (e.g., period=7)
        atr_long: Long-term ATR (e.g., period=14)

    Returns:
        pd.Series: Volatility ratio (>1 = expansion, <1 = contraction)
    """
    if len(atr_short) != len(atr_long):
        raise ValueError("ATR series must have equal length")

    # Avoid division by zero
    atr_long_safe = atr_long.replace(0, np.nan)

    # Calculate ratio
    ratio = atr_short / atr_long_safe

    # Fill NaN values with 1.0 (neutral ratio)
    ratio = ratio.fillna(1.0)

    return ratio


def session_range(
    high: pd.Series,
    low: pd.Series
) -> pd.Series:
    """
    PURPOSE: Calculate session range (high - low) for session analysis.
    Useful for identifying session strength and breakout levels.

    Args:
        high: High price series
        low: Low price series

    Returns:
        pd.Series: Session range values (in price units)
    """
    session_range_values = high - low

    return session_range_values


def trend_strength(
    adx: pd.Series,
    threshold: float = 25.0
) -> pd.Series:
    """
    PURPOSE: Classify trend strength as binary (trending vs ranging).
    Returns 1 if ADX is above threshold (strong trend), 0 if below (ranging).

    Args:
        adx: ADX series
        threshold: ADX threshold for trend classification (default 25)

    Returns:
        pd.Series: Binary values (1 = trending, 0 = ranging)
    """
    if threshold <= 0:
        raise ValueError("Threshold must be positive")

    # Classify as trending (1) or ranging (0)
    trend_strength_values = pd.Series(
        (adx >= threshold).astype(int),
        index=adx.index
    )

    return trend_strength_values
