"""
MT5 Bridge Module

PURPOSE: Provides factory function and exports for the MT5 bridge components.
This module encapsulates all MT5 RPyC connectivity via mt5linux library.

Exports:
    - MT5Connector: RPyC connection manager to MT5 Docker container
    - DataFeed: OHLCV data feed with dry-run support
    - OrderManager: Position management with idempotency and Redis
    - AccountInfo: Account reconciliation and balance tracking
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
            - host: str - MT5 Docker RPyC server host (e.g., "localhost")
            - port: int - MT5 Docker RPyC server port (e.g., 18861)
            - login: int - MT5 account login number
            - password: str - MT5 account password
            - server: str - MT5 server name (e.g., "VolatilityUltra-Demo")
            - redis_url: str - Redis connection URL (e.g., "redis://localhost:6379")
            - dry_run: bool - Enable dry-run mode with mock data (default: True)

    Returns:
        tuple[MT5Connector, DataFeed, OrderManager, AccountInfo]: Bridge components

    Raises:
        KeyError: If required settings keys are missing
        ConnectionError: If MT5 connection fails
    """
    # Extract settings
    host = settings.get("host", "localhost")
    port = settings.get("port", 18861)
    login = settings.get("login")
    password = settings.get("password")
    server = settings.get("server")
    redis_url = settings.get("redis_url", "redis://localhost:6379")
    dry_run = settings.get("dry_run", True)

    # Validate required settings
    if login is None:
        raise KeyError("settings['login'] is required")
    if password is None:
        raise KeyError("settings['password'] is required")
    if server is None:
        raise KeyError("settings['server'] is required")

    # Create connector
    connector = MT5Connector(
        host=host,
        port=port,
        login=login,
        password=password,
        server=server
    )

    # Create other components
    data_feed = DataFeed(connector=connector, dry_run=dry_run)
    order_manager = OrderManager(
        connector=connector,
        redis_url=redis_url,
        dry_run=dry_run
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
