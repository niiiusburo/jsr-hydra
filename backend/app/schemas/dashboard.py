"""
Dashboard-related Pydantic schemas for the JSR Hydra API.

Handles validation and serialization of dashboard summaries,
live updates, and comprehensive system state representations.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from .account import AccountResponse
from .allocation import AllocationResponse
from .regime import RegimeResponse
from .strategy import StrategyMetrics
from .trade import TradeResponse


class DashboardSummary(BaseModel):
    """
    Comprehensive dashboard summary containing system state.

    Attributes:
        account: Current account state
        regime: Current market regime (Optional)
        allocations: Current strategy allocations
        strategies: Active strategy metrics
        recent_trades: Recently executed trades
        equity_curve: Historical equity values
        system_status: Overall system status
        version: System version
    """

    model_config = ConfigDict(from_attributes=True)

    account: Optional[AccountResponse] = None
    regime: Optional[RegimeResponse] = None
    allocations: list[AllocationResponse] = []
    strategies: list[StrategyMetrics] = []
    recent_trades: list[TradeResponse] = []
    equity_curve: list[dict] = []
    system_status: str = "unknown"
    version: str = "1.0.0"
    mt5: Optional[dict] = None
    positions: list[dict] = []
    trading: Optional[dict] = None


class LiveUpdate(BaseModel):
    """
    Real-time event update for WebSocket/streaming.

    Attributes:
        event_type: Type of event (trade_opened, trade_closed, regime_change, etc.)
        data: Event payload dictionary
        timestamp: Event timestamp
    """

    model_config = ConfigDict(from_attributes=True)

    event_type: str
    data: dict
    timestamp: datetime
