"""
PURPOSE: Engine module exports for the JSR Hydra trading system.

Provides factory functions and main orchestrator exports for the core
trading engine which coordinates all strategy execution, risk management,
and MT5 bridge operations.

Exports:
    - TradingEngine: Main orchestrator class
    - RegimeDetector: Market regime detection
"""

from app.engine.engine import TradingEngine
from app.engine.regime_detector import RegimeDetector

__all__ = [
    "TradingEngine",
    "RegimeDetector",
]
