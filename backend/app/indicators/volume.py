"""
PURPOSE: Volume indicators for analyzing trading volume and money flow.
Includes OBV, VWAP, and Money Flow Index (MFI).
"""

import numpy as np
import pandas as pd


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """
    PURPOSE: Calculate On-Balance Volume (OBV) - accumulates volume based on price direction.

    Args:
        close: Close price series
        volume: Trading volume series

    Returns:
        pd.Series: OBV values (cumulative volume indicator)
    """
    # Calculate price changes
    price_diff = close.diff()

    # Initialize OBV
    obv_values = pd.Series(0, index=close.index, dtype='float64')

    # Calculate OBV
    obv_values.iloc[0] = volume.iloc[0]

    for i in range(1, len(close)):
        if price_diff.iloc[i] > 0:
            obv_values.iloc[i] = obv_values.iloc[i-1] + volume.iloc[i]
        elif price_diff.iloc[i] < 0:
            obv_values.iloc[i] = obv_values.iloc[i-1] - volume.iloc[i]
        else:
            obv_values.iloc[i] = obv_values.iloc[i-1]

    return obv_values


def vwap(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    volume: pd.Series
) -> pd.Series:
    """
    PURPOSE: Calculate Volume Weighted Average Price (VWAP) - average price weighted by volume.

    Args:
        high: High price series
        low: Low price series
        close: Close price series
        volume: Trading volume series

    Returns:
        pd.Series: VWAP values (shows fair value based on volume)
    """
    if (volume == 0).all():
        return pd.Series(0, index=close.index)

    # Calculate typical price
    typical_price = (high + low + close) / 3

    # Calculate cumulative typical price * volume
    tp_vol = typical_price * volume
    cum_tp_vol = tp_vol.cumsum()

    # Calculate cumulative volume
    cum_volume = volume.cumsum()

    # Avoid division by zero
    cum_volume = cum_volume.replace(0, np.nan)

    # Calculate VWAP
    vwap_values = cum_tp_vol / cum_volume

    return vwap_values


def mfi(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    volume: pd.Series,
    period: int = 14
) -> pd.Series:
    """
    PURPOSE: Calculate Money Flow Index (MFI) - combines price and volume.

    Args:
        high: High price series
        low: Low price series
        close: Close price series
        volume: Trading volume series
        period: MFI period (default 14)

    Returns:
        pd.Series: MFI values (0-100, >80 overbought, <20 oversold)
    """
    if period < 1:
        raise ValueError("Period must be >= 1")

    # Calculate typical price
    typical_price = (high + low + close) / 3

    # Calculate raw money flow
    raw_money_flow = typical_price * volume

    # Determine if positive or negative
    money_flow_sign = pd.Series(0, index=close.index, dtype='float64')
    price_diff = typical_price.diff()

    money_flow_sign[price_diff > 0] = 1
    money_flow_sign[price_diff < 0] = -1
    money_flow_sign[price_diff == 0] = 0

    # Calculate positive and negative money flow
    positive_flow = pd.Series(0, index=close.index, dtype='float64')
    negative_flow = pd.Series(0, index=close.index, dtype='float64')

    for i in range(len(close)):
        if money_flow_sign.iloc[i] > 0:
            positive_flow.iloc[i] = raw_money_flow.iloc[i]
        elif money_flow_sign.iloc[i] < 0:
            negative_flow.iloc[i] = raw_money_flow.iloc[i]

    # Calculate rolling sums
    positive_mf = positive_flow.rolling(window=period).sum()
    negative_mf = negative_flow.rolling(window=period).sum()

    # Avoid division by zero
    negative_mf = negative_mf.replace(0, 1)

    # Calculate money flow ratio
    money_flow_ratio = positive_mf / negative_mf

    # Calculate MFI
    mfi_values = 100 - (100 / (1 + money_flow_ratio))
    mfi_values = mfi_values.fillna(50)  # Default to 50 when no data

    return mfi_values
