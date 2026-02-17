"""
PURPOSE: Export configuration settings and constants for JSR Hydra.

This module centralizes access to all configuration settings and constants
used throughout the JSR Hydra trading system.
"""

from .constants import (
    DailyLossLimitPct,
    EventType,
    MaxDrawdownPct,
    OrderDirection,
    OrderStatus,
    RegimeType,
    Severity,
    StrategyCode,
    StrategyStatus,
    SUPPORTED_SYMBOLS,
    SystemStatus,
    TIMEFRAMES,
)
from .settings import settings

__all__ = [
    "settings",
    "RegimeType",
    "OrderDirection",
    "OrderStatus",
    "StrategyCode",
    "StrategyStatus",
    "SystemStatus",
    "Severity",
    "EventType",
    "SUPPORTED_SYMBOLS",
    "TIMEFRAMES",
    "MaxDrawdownPct",
    "DailyLossLimitPct",
]
