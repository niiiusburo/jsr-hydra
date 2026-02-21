"""
PURPOSE: Strategy module exports for JSR Hydra trading system.

Exports the BaseStrategy abstract class, all strategy implementations (A, B, C, D, E),
and StrategySignal model for use throughout the trading engine.
"""

from app.strategies.base import BaseStrategy
from app.strategies.strategy_a import StrategyA
from app.strategies.strategy_b import StrategyB
from app.strategies.strategy_c import StrategyC
from app.strategies.strategy_d import StrategyD
from app.strategies.strategy_e import StrategyE
from app.strategies.signals import StrategySignal

__all__ = [
    "BaseStrategy",
    "StrategyA",
    "StrategyB",
    "StrategyC",
    "StrategyD",
    "StrategyE",
    "StrategySignal",
]
