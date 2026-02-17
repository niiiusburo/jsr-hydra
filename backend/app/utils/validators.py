"""
PURPOSE: Input validation functions for trading parameters, symbols, and portfolio data.
Ensures data integrity before processing through trading system.
"""

from typing import Dict


SUPPORTED_SYMBOLS = ["XAUUSD", "BTCUSD", "EURUSD"]


def validate_symbol(symbol: str) -> bool:
    """
    PURPOSE: Validate that the provided symbol is supported by the system.

    Args:
        symbol: Trading symbol to validate.

    Returns:
        bool: True if symbol is in SUPPORTED_SYMBOLS, False otherwise.
    """
    return symbol in SUPPORTED_SYMBOLS


def validate_lots(lots: float, min_lot: float = 0.01, max_lot: float = 100.0) -> bool:
    """
    PURPOSE: Validate that lot size is within acceptable range.

    Args:
        lots: Lot size to validate.
        min_lot: Minimum allowed lot size (default 0.01).
        max_lot: Maximum allowed lot size (default 100.0).

    Returns:
        bool: True if min_lot <= lots <= max_lot, False otherwise.
    """
    return min_lot <= lots <= max_lot


def validate_price(price: float) -> bool:
    """
    PURPOSE: Validate that price is a positive number.

    Args:
        price: Price to validate.

    Returns:
        bool: True if price > 0, False otherwise.
    """
    return price > 0


def validate_allocation_weights(weights: Dict[str, float]) -> bool:
    """
    PURPOSE: Validate portfolio allocation weights.
    Checks that all weights are in [0, 1] and sum is <= 1.0.

    Args:
        weights: Dictionary of symbol -> weight.

    Returns:
        bool: True if all weights are valid and sum <= 1.0, False otherwise.
    """
    if not weights:
        return True

    # Check all weights are in [0, 1]
    for weight in weights.values():
        if weight < 0 or weight > 1:
            return False

    # Check sum is <= 1.0 (allowing for floating point precision)
    total = sum(weights.values())
    return total <= 1.0 + 1e-9


def validate_ohlcv(df) -> bool:
    """
    PURPOSE: Validate OHLCV (Open, High, Low, Close, Volume) dataframe.
    Checks for null values, valid price relationships, and non-negative volume.

    Args:
        df: pandas DataFrame with OHLC columns and Volume.

    Returns:
        bool: True if all OHLCV validations pass, False otherwise.
    """
    try:
        import pandas as pd
    except ImportError:
        return False

    if df is None or df.empty:
        return False

    required_columns = ["Open", "High", "Low", "Close", "Volume"]

    # Check all required columns exist
    if not all(col in df.columns for col in required_columns):
        return False

    # Check for null values in OHLC
    if df[["Open", "High", "Low", "Close"]].isnull().any().any():
        return False

    # Check Open > 0
    if (df["Open"] <= 0).any():
        return False

    # Check High >= Low
    if (df["High"] < df["Low"]).any():
        return False

    # Check Volume >= 0
    if (df["Volume"] < 0).any():
        return False

    return True
