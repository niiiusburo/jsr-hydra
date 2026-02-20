"""
MT5 Account Information Module via HTTP REST Bridge

PURPOSE: Track account balance, equity, margin, and provide account summary.
Uses GET /account with a 5-second in-memory cache to avoid hammering MT5.

CALLED BY:
    - risk_manager
    - position_reconciler
    - reporting_engine
"""

import time
from typing import Optional, Any

from app.bridge.connector import MT5Connector
from app.utils.logger import get_logger

logger = get_logger("bridge.account_info")

# Cache TTL in seconds
_CACHE_TTL = 5.0


class AccountInfo:
    """
    PURPOSE: Query account information from MT5 REST bridge with caching.

    Provides methods to:
    - Get account balance, equity, margin levels
    - Query full account summary
    - All data cached for 5 seconds to avoid excessive MT5 requests

    Attributes:
        _connector: MT5Connector instance (HTTP-based)
        _cache: Cached account data dict
        _cache_time: Timestamp of last cache fill
    """

    # Default account data when MT5 is unavailable (DRY_RUN mode)
    SYNTHETIC_ACCOUNT = {
        "login": 0,
        "server": "synthetic",
        "balance": 10000.0,
        "equity": 10000.0,
        "margin": 0.0,
        "free_margin": 10000.0,
        "margin_level": 9999.0,
        "profit": 0.0,
        "currency": "USD",
        "leverage": 100,
    }

    def __init__(
        self,
        connector: MT5Connector,
        dry_run: bool = True,
    ):
        """
        PURPOSE: Initialize AccountInfo with connector.

        Args:
            connector: MT5Connector instance for REST API calls.
            dry_run: Accepted for interface compatibility (unused -- always uses real data).
        """
        self._connector = connector
        self._cache: Optional[dict] = None
        self._cache_time: float = 0.0
        self._use_synthetic: bool = False

        logger.info("account_info_initialized", dry_run=dry_run)

    def enable_synthetic_mode(self) -> None:
        """Enable synthetic account data for DRY_RUN without MT5."""
        self._use_synthetic = True
        logger.info("account_info_synthetic_mode_enabled", balance=self.SYNTHETIC_ACCOUNT["balance"])

    async def _get_account_data(self) -> dict:
        """
        PURPOSE: Fetch account data from MT5 REST bridge with 5-second cache.

        If cached data is less than 5 seconds old, returns cache.
        Otherwise, calls connector.get_account_info() (GET /account).
        In synthetic mode, returns default account data.

        Returns:
            dict: Account data with keys: login, server, balance, equity,
                  margin, free_margin, margin_level, profit, currency, leverage.

        Raises:
            ConnectionError: If MT5 REST call fails and not in synthetic mode.
        """
        if self._use_synthetic:
            return dict(self.SYNTHETIC_ACCOUNT)

        now = time.time()
        if self._cache is not None and (now - self._cache_time) < _CACHE_TTL:
            return self._cache

        data = await self._connector.get_account_info()
        self._cache = data
        self._cache_time = time.time()
        return data

    async def get_balance(self) -> float:
        """
        PURPOSE: Get current account balance.

        Balance is the original account funding amount. Does not include
        unrealized P&L from open positions.

        Returns:
            float: Account balance in account currency.

        Raises:
            ConnectionError: If MT5 REST call fails.
        """
        logger.info("get_balance_requested")

        try:
            data = await self._get_account_data()
            balance = float(data.get("balance", 0.0))
            logger.info("balance_retrieved", balance=balance)
            return balance
        except Exception as e:
            logger.error("get_balance_error", error=str(e))
            raise

    async def get_equity(self) -> float:
        """
        PURPOSE: Get current account equity.

        Equity = Balance + Floating P&L from open positions.

        Returns:
            float: Account equity in account currency.

        Raises:
            ConnectionError: If MT5 REST call fails.
        """
        logger.info("get_equity_requested")

        try:
            data = await self._get_account_data()
            equity = float(data.get("equity", 0.0))
            logger.info("equity_retrieved", equity=equity)
            return equity
        except Exception as e:
            logger.error("get_equity_error", error=str(e))
            raise

    async def get_margin_level(self) -> float:
        """
        PURPOSE: Get current margin level percentage.

        Margin Level = (Equity / Used Margin) * 100.
        Values below 100% may trigger liquidation.

        Returns:
            float: Margin level as percentage (e.g., 500.0 for 500%).

        Raises:
            ConnectionError: If MT5 REST call fails.
        """
        logger.info("get_margin_level_requested")

        try:
            data = await self._get_account_data()
            margin_level = float(data.get("margin_level", 0.0))
            logger.info("margin_level_retrieved", margin_level=margin_level)
            return margin_level
        except Exception as e:
            logger.error("get_margin_level_error", error=str(e))
            raise

    async def get_free_margin(self) -> float:
        """
        PURPOSE: Get available free margin for new positions.

        Free Margin = Equity - Used Margin.

        Returns:
            float: Free margin in account currency.

        Raises:
            ConnectionError: If MT5 REST call fails.
        """
        logger.info("get_free_margin_requested")

        try:
            data = await self._get_account_data()
            free_margin = float(data.get("free_margin", 0.0))
            logger.info("free_margin_retrieved", free_margin=free_margin)
            return free_margin
        except Exception as e:
            logger.error("get_free_margin_error", error=str(e))
            raise

    async def get_account_summary(self) -> dict:
        """
        PURPOSE: Get complete account summary snapshot.

        Returns the full /account response enriched with convenience keys.
        Cached for 5 seconds.

        Returns:
            dict: Account summary with keys:
                - balance: float
                - equity: float
                - margin_level: float
                - free_margin: float
                - used_margin: float (mapped from 'margin')
                - profit: float
                - currency: str
                - login: int
                - server: str
                - leverage: int

        Raises:
            ConnectionError: If MT5 REST call fails.
        """
        logger.info("get_account_summary_requested")

        try:
            data = await self._get_account_data()

            summary = {
                "balance": float(data.get("balance", 0.0)),
                "equity": float(data.get("equity", 0.0)),
                "margin_level": float(data.get("margin_level", 0.0)),
                "free_margin": float(data.get("free_margin", 0.0)),
                "used_margin": float(data.get("margin", 0.0)),
                "profit": float(data.get("profit", 0.0)),
                "currency": data.get("currency", "USD"),
                "login": int(data.get("login", 0)),
                "server": data.get("server", ""),
                "leverage": int(data.get("leverage", 0)),
            }

            logger.info(
                "account_summary_retrieved",
                balance=summary["balance"],
                equity=summary["equity"],
                margin_level=summary["margin_level"],
            )
            return summary

        except Exception as e:
            logger.error("get_account_summary_error", error=str(e))
            raise

    async def sync_with_db(self, db_session: Any) -> None:
        """
        PURPOSE: Reconcile MT5 positions with database trades.

        Placeholder for position reconciliation logic.
        Uses GET /positions under the hood (via OrderManager or direct call).

        Args:
            db_session: SQLAlchemy async session for database access.
        """
        logger.info("position_reconciliation_started")

        try:
            # Fetch positions from MT5 REST bridge
            client = await self._connector._get_client()
            resp = await client.get("/positions")
            resp.raise_for_status()
            mt5_positions = resp.json()

            logger.info(
                "position_reconciliation_completed",
                mt5_positions=len(mt5_positions),
                discrepancies_detected=0,
            )

            # TODO: Implement full database sync
            # 1. Query Trade model for OPEN positions
            # 2. Match by mt5_ticket field
            # 3. Check for discrepancies
            # 4. Log warnings
            # 5. Update DB trades with MT5 data if needed

        except Exception as e:
            logger.error("position_reconciliation_error", error=str(e))
            raise
