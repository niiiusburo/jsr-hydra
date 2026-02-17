"""
PURPOSE: Volatility indicators for measuring price movement and establishing
support/resistance levels. Includes ATR, Bollinger Bands, Keltner Channels,
and Historical Volatility.
"""

import numpy as np
import pandas as pd
from typing import Tuple


def atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14
) -> pd.Series:
    """
    PURPOSE: Calculate Average True Range (ATR) - measures market volatility.

    Args:
        high: High price series
        low: Low price series
        close: Close price series
        period: ATR period (default 14)

    Returns:
        pd.Series: ATR values (in price units, higher = more volatile)
    """
    if period < 1:
        raise ValueError("Period must be >= 1")

    # Calculate true range components
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()

    # Get maximum true range
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # Calculate ATR using EMA
    atr_values = tr.ewm(span=period, adjust=False).mean()

    return atr_values


def bollinger_bands(
    close: pd.Series,
    period: int = 20,
    std_dev: float = 2.0
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    PURPOSE: Calculate Bollinger Bands - identifies volatility and extremes.

    Args:
        close: Close price series
        period: Moving average period (default 20)
        std_dev: Standard deviation multiplier (default 2.0)

    Returns:
        Tuple[pd.Series, pd.Series, pd.Series]: (upper_band, middle_band, lower_band)
            - middle_band: SMA of close prices
            - upper_band: middle + (std_dev * standard deviation)
            - lower_band: middle - (std_dev * standard deviation)
    """
    if period < 1:
        raise ValueError("Period must be >= 1")
    if std_dev <= 0:
        raise ValueError("Standard deviation multiplier must be positive")

    # Calculate middle band (SMA)
    middle_band = close.rolling(window=period).mean()

    # Calculate standard deviation
    std = close.rolling(window=period).std()

    # Calculate upper and lower bands
    upper_band = middle_band + (std_dev * std)
    lower_band = middle_band - (std_dev * std)

    return upper_band, middle_band, lower_band


def keltner_channels(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    ema_period: int = 20,
    atr_period: int = 10,
    multiplier: float = 1.5
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    PURPOSE: Calculate Keltner Channels - volatility-based support/resistance.

    Args:
        high: High price series
        low: Low price series
        close: Close price series
        ema_period: EMA period for middle band (default 20)
        atr_period: ATR period (default 10)
        multiplier: ATR multiplier for bands (default 1.5)

    Returns:
        Tuple[pd.Series, pd.Series, pd.Series]: (upper_band, middle_band, lower_band)
            - middle_band: EMA of close
            - upper_band: middle + (multiplier * ATR)
            - lower_band: middle - (multiplier * ATR)
    """
    if ema_period < 1 or atr_period < 1:
        raise ValueError("All periods must be >= 1")
    if multiplier <= 0:
        raise ValueError("Multiplier must be positive")

    # Calculate middle band (EMA)
    middle_band = close.ewm(span=ema_period, adjust=False).mean()

    # Calculate ATR
    atr_values = atr(high, low, close, atr_period)

    # Calculate bands
    upper_band = middle_band + (multiplier * atr_values)
    lower_band = middle_band - (multiplier * atr_values)

    return upper_band, middle_band, lower_band


def historical_volatility(
    close: pd.Series,
    period: int = 20
) -> pd.Series:
    """
    PURPOSE: Calculate Historical Volatility - measures standard deviation of returns.

    Args:
        close: Close price series
        period: Lookback period (default 20)

    Returns:
        pd.Series: Historical volatility as percentage (higher = more volatile)
    """
    if period < 1:
        raise ValueError("Period must be >= 1")

    # Calculate log returns
    returns = np.log(close / close.shift(1))

    # Calculate rolling standard deviation
    historical_vol = returns.rolling(window=period).std() * np.sqrt(252)  # Annualized

    # Convert to percentage
    historical_vol = historical_vol * 100

    return historical_vol
