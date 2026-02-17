"""
PURPOSE: Risk management module for JSR Hydra trading system.

Provides kill switch, position sizing, and comprehensive risk validation
for all trading operations.

Exports:
    - RiskManager: Main orchestrator for risk checks
    - KillSwitch: Emergency trading halt mechanism
    - PositionSizer: Position size calculator
    - RiskCheckResult: Risk check decision model
    - RiskMetrics: Risk metrics snapshot model
"""

from app.risk.kill_switch import KillSwitch
from app.risk.position_sizer import PositionSizer
from app.risk.risk_manager import RiskManager
from app.risk.risk_models import RiskCheckResult, RiskMetrics

__all__ = [
    "RiskManager",
    "KillSwitch",
    "PositionSizer",
    "RiskCheckResult",
    "RiskMetrics",
]
