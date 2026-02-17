"""
Business logic layer for JSR Hydra trading system.

PURPOSE: Services provide the business logic layer between API routes and database models.
They handle domain operations, validation, and event publishing while remaining stateless
and database session-aware.

CALLED BY: API routes in app.api

Services:
    - TradeService: Trade creation, querying, updating, and statistics
    - StrategyService: Strategy management and performance metrics
    - AccountService: Account state, equity tracking, and health monitoring
    - DashboardService: Comprehensive dashboard data assembly
    - RegimeService: Market regime detection and history
"""

from app.services.trade_service import TradeService
from app.services.strategy_service import StrategyService
from app.services.account_service import AccountService
from app.services.dashboard_service import DashboardService
from app.services.regime_service import RegimeService

__all__ = [
    "TradeService",
    "StrategyService",
    "AccountService",
    "DashboardService",
    "RegimeService",
]
