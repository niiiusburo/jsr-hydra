"""
MT5 Bridge Module

PURPOSE: Provides factory function and exports for the MT5 bridge components.
This module encapsulates all MT5 connectivity via HTTP REST bridge (httpx).

Exports:
    - MT5Connector: HTTP connection manager to MT5 REST bridge
    - DataFeed: OHLCV data feed (always real MT5 data)
    - OrderManager: Position management with idempotency and Redis
    - AccountInfo: Account balance/equity tracking with caching
    - create_bridge: Factory function to instantiate all bridge components
"""

from app.bridge.connector import MT5Connector
from app.bridge.data_feed import DataFeed
from app.bridge.order_manager import OrderManager
from app.bridge.account_info import AccountInfo


def create_bridge(
    settings: dict,
) -> tuple[MT5Connector, DataFeed, OrderManager, AccountInfo]:
    """
    PURPOSE: Factory function to instantiate all MT5 bridge components.

    Initializes MT5Connector, DataFeed, OrderManager, and AccountInfo
    with settings from config. Creates and returns the complete bridge tuple.

    Args:
        settings: Dict containing:
            - mt5_rest_url: str - MT5 REST bridge URL (default "http://jsr-mt5:18812")
            - redis_url: str - Redis connection URL (default "redis://localhost:6379")
            - dry_run: bool - Enable dry-run mode (default True)
            - max_test_lots: float - Max lot size during testing (default 0.01)

    Returns:
        tuple[MT5Connector, DataFeed, OrderManager, AccountInfo]: Bridge components
    """
    # Extract settings
    mt5_rest_url = settings.get("mt5_rest_url", "http://jsr-mt5:18812")
    redis_url = settings.get("redis_url", "redis://localhost:6379")
    dry_run = settings.get("dry_run", True)
    max_test_lots = settings.get("max_test_lots", 0.01)

    # Create connector (HTTP-based)
    connector = MT5Connector(base_url=mt5_rest_url)

    # Create other components
    data_feed = DataFeed(connector=connector, dry_run=dry_run)
    order_manager = OrderManager(
        connector=connector,
        redis_url=redis_url,
        dry_run=dry_run,
        max_test_lots=max_test_lots,
    )
    account_info = AccountInfo(connector=connector, dry_run=dry_run)

    return connector, data_feed, order_manager, account_info


__all__ = [
    "MT5Connector",
    "DataFeed",
    "OrderManager",
    "AccountInfo",
    "create_bridge",
]
