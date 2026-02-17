"""
Pydantic v2 schemas for JSR Hydra trading system API.

This module exports all schema classes used throughout the API
for request/response validation and documentation.
"""

from .account import AccountResponse, FollowerResponse
from .allocation import AllocationResponse, AllocationUpdate, AllocationSummary
from .dashboard import DashboardSummary, LiveUpdate
from .regime import RegimeResponse, RegimeHistory
from .strategy import StrategyResponse, StrategyUpdate, StrategyMetrics
from .system import (
    HealthCheck,
    VersionInfo,
    EventLogResponse,
    LoginRequest,
    TokenResponse,
)
from .trade import TradeCreate, TradeUpdate, TradeResponse, TradeList, TradeStats

__all__ = [
    # Trade schemas
    "TradeCreate",
    "TradeUpdate",
    "TradeResponse",
    "TradeList",
    "TradeStats",
    # Strategy schemas
    "StrategyResponse",
    "StrategyUpdate",
    "StrategyMetrics",
    # Regime schemas
    "RegimeResponse",
    "RegimeHistory",
    # Allocation schemas
    "AllocationResponse",
    "AllocationUpdate",
    "AllocationSummary",
    # Account schemas
    "AccountResponse",
    "FollowerResponse",
    # Dashboard schemas
    "DashboardSummary",
    "LiveUpdate",
    # System schemas
    "HealthCheck",
    "VersionInfo",
    "EventLogResponse",
    "LoginRequest",
    "TokenResponse",
]
