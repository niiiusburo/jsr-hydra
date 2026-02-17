"""
PURPOSE: Momentum indicators for identifying overbought/oversold conditions
and measuring price velocity. Includes RSI, Stochastic, Williams %R, CCI, and ROC.
"""

import numpy as np
import pandas as pd
from typing import Tuple


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """
    PURPOSE: Calculate Relative Strength Index (RSI) - measures momentum.

    Args:
        close: Close price series
        period: RSI period (default 14)

    Returns:
        pd.Series: RSI values (0-100, >70 overbought, <30 oversold)
    """
    if period < 1:
        raise ValueError("Period must be >= 1")

    # Calculate changes
    delta = close.diff()

    # Separate gains and losses
    gains = delta.copy()
    losses = delta.copy()

    gains[gains < 0] = 0
    losses[losses > 0] = 0
    losses = losses.abs()

    # Calculate average gain and loss
    avg_gain = gains.rolling(window=period).mean()
    avg_loss = losses.rolling(window=period).mean()

    # Calculate RS and RSI
    rs = avg_gain / avg_loss
    # When avg_loss is 0 (all gains), RS is inf → RSI should be 100
    # When avg_gain is 0 (all losses), RS is 0 → RSI should be 0
    rsi_values = 100 - (100 / (1 + rs))
    # Replace NaN from 0/0 with 50, inf cases resolve naturally
    rsi_values = rsi_values.replace([np.inf, -np.inf], np.nan)
    rsi_values = rsi_values.fillna(50)  # Default to 50 when no data

    return rsi_values


def stochastic(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    k_period: int = 14,
    d_period: int = 3
) -> Tuple[pd.Series, pd.Series]:
    """
    PURPOSE: Calculate Stochastic Oscillator - identifies momentum extremes.

    Args:
        high: High price series
        low: Low price series
        close: Close price series
        k_period: K line period (default 14)
        d_period: D line (signal) period (default 3)

    Returns:
        Tuple[pd.Series, pd.Series]: (%K line, %D line)
            Both range 0-100, >80 overbought, <20 oversold
    """
    if k_period < 1 or d_period < 1:
        raise ValueError("All periods must be >= 1")

    # Calculate highest high and lowest low over k_period
    highest_high = high.rolling(window=k_period).max()
    lowest_low = low.rolling(window=k_period).min()

    # Calculate %K
    k_line = 100 * (close - lowest_low) / (highest_high - lowest_low)
    k_line = k_line.fillna(50)  # Default when range is zero

    # Calculate %D (moving average of %K)
    d_line = k_line.rolling(window=d_period).mean()

    return k_line, d_line


def williams_r(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14
) -> pd.Series:
    """
    PURPOSE: Calculate Williams %R - momentum oscillator similar to Stochastic.

    Args:
        high: High price series
        low: Low price series
        close: Close price series
        period: Williams %R period (default 14)

    Returns:
        pd.Series: Williams %R values (-100 to 0, -20 overbought, -80 oversold)
    """
    if period < 1:
        raise ValueError("Period must be >= 1")

    # Calculate highest high and lowest low
    highest_high = high.rolling(window=period).max()
    lowest_low = low.rolling(window=period).min()

    # Calculate Williams %R
    williams_r_values = -100 * (highest_high - close) / (highest_high - lowest_low)
    williams_r_values = williams_r_values.fillna(-50)  # Default value

    return williams_r_values


def cci(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 20
) -> pd.Series:
    """
    PURPOSE: Calculate Commodity Channel Index (CCI) - measures deviation from average price.

    Args:
        high: High price series
        low: Low price series
        close: Close price series
        period: CCI period (default 20)

    Returns:
        pd.Series: CCI values (>100 overbought, <-100 oversold)
    """
    if period < 1:
        raise ValueError("Period must be >= 1")

    # Calculate typical price
    typical_price = (high + low + close) / 3

    # Calculate SMA of typical price
    sma_tp = typical_price.rolling(window=period).mean()

    # Calculate mean deviation
    mean_deviation = (typical_price - sma_tp).rolling(window=period).mean().abs()

    # Avoid division by zero
    mean_deviation = mean_deviation.replace(0, 1)

    # Calculate CCI
    cci_values = (typical_price - sma_tp) / (0.015 * mean_deviation)

    return cci_values


def roc(close: pd.Series, period: int = 12) -> pd.Series:
    """
    PURPOSE: Calculate Rate of Change (ROC) - measures price momentum over time.

    Args:
        close: Close price series
        period: ROC period (default 12)

    Returns:
        pd.Series: ROC values in percentage (positive = upward momentum)
    """
    if period < 1:
        raise ValueError("Period must be >= 1")

    # Calculate price change
    price_change = close - close.shift(period)

    # Calculate ROC as percentage
    roc_values = (price_change / close.shift(period)) * 100
    roc_values = roc_values.fillna(0)  # Fill NaN with 0

    return roc_values
