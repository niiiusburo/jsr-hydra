"""
PURPOSE: Mathematical utilities for trading calculations including position sizing,
risk metrics, and portfolio statistics.
"""

import numpy as np
from typing import List, Dict, Optional


def round_lots(lots: float, step: float = 0.01) -> float:
    """
    PURPOSE: Round lot size to the nearest step increment.

    Args:
        lots: Lot size to round.
        step: Rounding step (default 0.01).

    Returns:
        float: Rounded lot size.
    """
    return round(lots / step) * step


def calculate_pip_value(symbol: str, lots: float) -> float:
    """
    PURPOSE: Calculate the pip value in account currency for a given symbol and lot size.
    Uses simplified pip values for common trading pairs.

    Args:
        symbol: Trading symbol (XAUUSD, EURUSD, BTCUSD, etc.).
        lots: Position size in lots.

    Returns:
        float: Pip value in account currency.
    """
    pip_values = {
        "XAUUSD": 10.0,
        "EURUSD": 10.0,
        "BTCUSD": 1.0,
    }

    base_pip = pip_values.get(symbol, 10.0)
    return lots * base_pip


def calculate_lot_size(
    equity: float,
    risk_pct: float,
    sl_points: float,
    pip_value_per_lot: float
) -> float:
    """
    PURPOSE: Calculate position size (lot size) based on equity, risk percentage, and stop loss.
    Formula: lots = (equity * risk_pct / 100) / (sl_points * pip_value_per_lot)
    Clamps result to [0.01, 100.0] and rounds to 0.01 step.

    Args:
        equity: Account equity in currency units.
        risk_pct: Risk percentage of equity (e.g., 2.0 for 2%).
        sl_points: Stop loss distance in points/pips.
        pip_value_per_lot: Pip value per lot for the symbol.

    Returns:
        float: Calculated and clamped lot size.
    """
    if sl_points <= 0 or pip_value_per_lot <= 0:
        return 0.01

    risk_amount = (equity * risk_pct) / 100.0
    lots = risk_amount / (sl_points * pip_value_per_lot)

    # Clamp to [0.01, 100.0] and round
    lots = max(0.01, min(100.0, lots))
    return round_lots(lots, step=0.01)


def calculate_drawdown(peak: float, current: float) -> float:
    """
    PURPOSE: Calculate percentage drawdown from peak equity to current value.
    Formula: ((peak - current) / peak) * 100

    Args:
        peak: Peak equity value.
        current: Current equity value.

    Returns:
        float: Drawdown percentage. Returns 0.0 if peak is 0 or current > peak.
    """
    if peak <= 0:
        return 0.0

    drawdown = ((peak - current) / peak) * 100.0
    return max(0.0, drawdown)  # Drawdown is non-negative


def calculate_sharpe(returns: List[float], risk_free: float = 0.0) -> float:
    """
    PURPOSE: Calculate Sharpe ratio for a series of returns.
    Formula: (mean(returns) - risk_free_rate) / std(returns)

    Args:
        returns: List of return values (e.g., daily returns).
        risk_free: Risk-free rate (default 0.0).

    Returns:
        float: Sharpe ratio. Returns 0.0 if returns list is empty or std is zero.
    """
    if not returns or len(returns) == 0:
        return 0.0

    returns_array = np.array(returns)
    mean_return = np.mean(returns_array)
    std_return = np.std(returns_array)

    if std_return == 0:
        return 0.0

    sharpe = (mean_return - risk_free) / std_return
    return float(sharpe)


def calculate_profit_factor(wins: List[float], losses: List[float]) -> float:
    """
    PURPOSE: Calculate profit factor (sum of wins / absolute sum of losses).
    Indicates trading strategy profitability.

    Args:
        wins: List of winning trade amounts (positive values).
        losses: List of losing trade amounts (negative values).

    Returns:
        float: Profit factor. Returns 0.0 if no losses or both lists empty.
    """
    total_wins = sum(wins) if wins else 0.0
    total_losses = sum(losses) if losses else 0.0

    if abs(total_losses) == 0:
        return 0.0

    profit_factor = total_wins / abs(total_losses)
    return float(profit_factor)


def normalize_weights(weights: Dict[str, float]) -> Dict[str, float]:
    """
    PURPOSE: Normalize allocation weights so they sum to 1.0.
    Handles edge cases like zero sum or empty weights.

    Args:
        weights: Dictionary of symbol -> weight.

    Returns:
        dict: Normalized weights summing to 1.0. Returns empty dict if sum is 0.
    """
    if not weights:
        return {}

    total = sum(weights.values())

    if total == 0:
        return {}

    return {symbol: weight / total for symbol, weight in weights.items()}
