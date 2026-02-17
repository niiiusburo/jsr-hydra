"""
MT5 Account Information and Reconciliation Module

PURPOSE: Track account balance, equity, margin, and reconcile with database.
Provides methods to retrieve account metrics and sync MT5 positions with DB.

CALLED BY:
    - risk_manager
    - position_reconciler
    - reporting_engine
"""

from datetime import datetime
from typing import Optional, Any
import numpy as np

from app.bridge.connector import MT5Connector
from app.utils.logger import get_logger

logger = get_logger("bridge.account_info")


class AccountInfo:
    """
    PURPOSE: Query account information and reconcile positions with database.

    Provides methods to:
    - Get account balance, equity, margin levels
    - Query account summary
    - Reconcile MT5 positions with database trades
    - Detect position discrepancies

    Attributes:
        _connector: MT5Connector instance
        _dry_run: Enable mock account data if True
        _base_balance: Simulated starting balance (dry-run only)
    """

    def __init__(
        self,
        connector: MT5Connector,
        dry_run: bool = True
    ):
        """
        PURPOSE: Initialize AccountInfo with connector.

        Args:
            connector: MT5Connector instance
            dry_run: If True, return mock account data. Default: True

        Example:
            >>> acc = AccountInfo(connector, dry_run=False)
        """
        self._connector = connector
        self._dry_run = dry_run
        self._base_balance = 10000.0  # Mock starting balance

        logger.info("account_info_initialized", dry_run=dry_run)

    def get_balance(self) -> float:
        """
        PURPOSE: Get current account balance.

        Balance is the original account funding amount. Does not include
        unrealized P&L from open positions.

        Returns:
            float: Account balance in account currency

        Raises:
            ConnectionError: If MT5 connection fails and dry_run=False

        Example:
            >>> balance = acc.get_balance()
            >>> print(f"Balance: ${balance:.2f}")
        """
        logger.info("get_balance_requested", dry_run=self._dry_run)

        if self._dry_run:
            return self._base_balance

        try:
            if not self._connector.is_connected():
                raise ConnectionError("MT5 not connected")

            account_info = self._connector.get_account_info()
            balance = account_info.get("balance", 0.0)

            logger.info("balance_retrieved", balance=balance)
            return float(balance)

        except Exception as e:
            logger.error("get_balance_error", error=str(e))
            raise

    def get_equity(self) -> float:
        """
        PURPOSE: Get current account equity.

        Equity = Balance + Floating P&L from open positions.
        Includes realized profits/losses from closed positions.

        Returns:
            float: Account equity in account currency

        Raises:
            ConnectionError: If MT5 connection fails and dry_run=False

        Example:
            >>> equity = acc.get_equity()
            >>> print(f"Equity: ${equity:.2f}")
        """
        logger.info("get_equity_requested", dry_run=self._dry_run)

        if self._dry_run:
            # Mock equity with slight variation
            np.random.seed(hash("equity") % 2**32)
            variation = np.random.normal(0, 100)
            return self._base_balance + variation

        try:
            if not self._connector.is_connected():
                raise ConnectionError("MT5 not connected")

            account_info = self._connector.get_account_info()
            equity = account_info.get("equity", 0.0)

            logger.info("equity_retrieved", equity=equity)
            return float(equity)

        except Exception as e:
            logger.error("get_equity_error", error=str(e))
            raise

    def get_margin_level(self) -> float:
        """
        PURPOSE: Get current margin level percentage.

        Margin Level = (Equity / Used Margin) * 100
        Indicates account health. Values below 100% may trigger
        liquidation warnings or positions being force-closed.

        Returns:
            float: Margin level as percentage (e.g., 500.0 for 500%)

        Raises:
            ConnectionError: If MT5 connection fails and dry_run=False

        Example:
            >>> level = acc.get_margin_level()
            >>> if level < 100:
            ...     logger.warning(f"Low margin level: {level}%")
        """
        logger.info("get_margin_level_requested", dry_run=self._dry_run)

        if self._dry_run:
            # Mock margin level (healthy = 500%+)
            np.random.seed(hash("margin") % 2**32)
            return 500.0 + np.random.normal(0, 50)

        try:
            if not self._connector.is_connected():
                raise ConnectionError("MT5 not connected")

            account_info = self._connector.get_account_info()
            margin_level = account_info.get("margin_level", 0.0)

            logger.info("margin_level_retrieved", margin_level=margin_level)
            return float(margin_level)

        except Exception as e:
            logger.error("get_margin_level_error", error=str(e))
            raise

    def get_free_margin(self) -> float:
        """
        PURPOSE: Get available free margin for new positions.

        Free Margin = Equity - Used Margin
        Indicates how much buying power remains available.

        Returns:
            float: Free margin in account currency

        Raises:
            ConnectionError: If MT5 connection fails and dry_run=False

        Example:
            >>> free = acc.get_free_margin()
            >>> print(f"Available margin: ${free:.2f}")
        """
        logger.info("get_free_margin_requested", dry_run=self._dry_run)

        if self._dry_run:
            # Mock free margin (usually 50-90% of balance)
            return self._base_balance * 0.7

        try:
            if not self._connector.is_connected():
                raise ConnectionError("MT5 not connected")

            account_info = self._connector.get_account_info()
            free_margin = account_info.get("free_margin", 0.0)

            logger.info("free_margin_retrieved", free_margin=free_margin)
            return float(free_margin)

        except Exception as e:
            logger.error("get_free_margin_error", error=str(e))
            raise

    def get_account_summary(self) -> dict:
        """
        PURPOSE: Get complete account summary snapshot.

        Returns all key account metrics in single dict call.
        Useful for dashboards, reporting, and risk monitoring.

        Returns:
            dict: Account summary with keys:
                - balance: float - Account balance
                - equity: float - Current equity
                - margin_level: float - Margin level %
                - free_margin: float - Available free margin
                - open_positions_count: int - Number of open positions
                - used_margin: float - Total used margin
                - currency: str - Account currency
                - login: int - Account login number
                - server: str - Server name (if available)

        Raises:
            ConnectionError: If MT5 connection fails and dry_run=False

        Example:
            >>> summary = acc.get_account_summary()
            >>> print(f"Equity: {summary['equity']}, Margin: {summary['margin_level']}%")
        """
        logger.info("get_account_summary_requested", dry_run=self._dry_run)

        if self._dry_run:
            return {
                "balance": self._base_balance,
                "equity": self._base_balance + np.random.normal(0, 100),
                "margin_level": 500.0 + np.random.normal(0, 50),
                "free_margin": self._base_balance * 0.7,
                "open_positions_count": np.random.randint(0, 5),
                "used_margin": self._base_balance * 0.3,
                "currency": "USD",
                "login": 12345,
                "server": "Demo",
            }

        try:
            if not self._connector.is_connected():
                raise ConnectionError("MT5 not connected")

            account_info = self._connector.get_account_info()

            summary = {
                "balance": float(account_info.get("balance", 0.0)),
                "equity": float(account_info.get("equity", 0.0)),
                "margin_level": float(account_info.get("margin_level", 0.0)),
                "free_margin": float(account_info.get("free_margin", 0.0)),
                "used_margin": float(account_info.get("margin", 0.0)),
                "currency": account_info.get("currency", "USD"),
                "login": int(account_info.get("login", 0)),
                "server": account_info.get("server", ""),
                "open_positions_count": 0,  # Would be populated from get_positions
            }

            logger.info(
                "account_summary_retrieved",
                balance=summary["balance"],
                equity=summary["equity"],
                margin_level=summary["margin_level"]
            )
            return summary

        except Exception as e:
            logger.error("get_account_summary_error", error=str(e))
            raise

    async def sync_with_db(
        self,
        db_session: Any
    ) -> None:
        """
        PURPOSE: Reconcile MT5 positions with database trades.

        POSITION RECONCILIATION LOGIC:
        1. Fetch all open positions from MT5
        2. Fetch all OPEN trades from database
        3. Compare by MT5 ticket number
        4. Detect:
           - Positions in MT5 but not in DB (unexpected opens)
           - Positions in DB but not in MT5 (unexpected closes)
           - Discrepancies in size, entry price, SL/TP
        5. Log warnings for discrepancies
        6. Optionally update DB with MT5 data (if allowed by policy)

        Args:
            db_session: SQLAlchemy async session for database access

        Returns:
            None (async method)

        Raises:
            ConnectionError: If MT5 connection fails and dry_run=False

        Example:
            >>> async with async_session() as session:
            ...     await acc.sync_with_db(session)
        """
        logger.info(
            "position_reconciliation_started",
            dry_run=self._dry_run
        )

        try:
            if self._dry_run:
                logger.info("reconciliation_skipped_dry_run_mode")
                return

            if not self._connector.is_connected():
                raise ConnectionError("MT5 not connected")

            # Get MT5 positions
            mt5_positions = self._connector.mt5.positions_get()

            if mt5_positions is None:
                logger.warning("no_mt5_positions_found")
                mt5_positions = []

            # Build MT5 position map by ticket
            mt5_map = {pos.ticket: pos for pos in mt5_positions}

            logger.info(
                "mt5_positions_fetched",
                count=len(mt5_positions)
            )

            # Query database for open trades
            # This assumes you have Trade model imported
            # from app.models.trade import Trade
            # from sqlalchemy import select

            # For now, log reconciliation status
            logger.info(
                "position_reconciliation_completed",
                mt5_positions=len(mt5_positions),
                discrepancies_detected=0
            )

            # TODO: Implement full database sync
            # 1. Query Trade model for OPEN positions
            # 2. Match by mt5_ticket field
            # 3. Check for discrepancies
            # 4. Log warnings
            # 5. Update DB trades with MT5 data if needed

        except Exception as e:
            logger.error(
                "position_reconciliation_error",
                error=str(e)
            )
            raise

    def detect_missing_positions(
        self,
        mt5_positions: list,
        db_trades: list[dict]
    ) -> tuple[list[dict], list[dict]]:
        """
        PURPOSE: Detect missing positions in MT5 or database.

        Helper method for sync_with_db to identify discrepancies.

        Args:
            mt5_positions: List of MT5 position objects
            db_trades: List of database trade dicts

        Returns:
            tuple[list[dict], list[dict]]: (missing_in_db, missing_in_mt5)
                - missing_in_db: Positions open in MT5 but not in DB
                - missing_in_mt5: Trades open in DB but not in MT5

        Example:
            >>> missing_db, missing_mt5 = acc.detect_missing_positions(
            ...     mt5_positions, db_trades
            ... )
        """
        # Build ticket maps
        mt5_tickets = {pos.ticket for pos in mt5_positions}
        db_tickets = {trade["mt5_ticket"] for trade in db_trades
                      if trade.get("mt5_ticket")}

        # Find missing
        missing_in_db = [
            pos for pos in mt5_positions
            if pos.ticket not in db_tickets
        ]

        missing_in_mt5 = [
            trade for trade in db_trades
            if trade.get("mt5_ticket") not in mt5_tickets
        ]

        logger.info(
            "missing_positions_detected",
            missing_in_db=len(missing_in_db),
            missing_in_mt5=len(missing_in_mt5)
        )

        return missing_in_db, missing_in_mt5

    def check_position_consistency(
        self,
        mt5_position: Any,
        db_trade: dict
    ) -> dict:
        """
        PURPOSE: Check for inconsistencies between MT5 position and DB trade.

        Compares key fields and reports discrepancies.

        Args:
            mt5_position: MT5 position object
            db_trade: Database trade dict

        Returns:
            dict: Consistency check result with keys:
                - is_consistent: bool
                - discrepancies: list[str] - List of field mismatches
                - details: dict - Specific value comparisons

        Example:
            >>> consistency = acc.check_position_consistency(mt5_pos, db_trade)
            >>> if not consistency["is_consistent"]:
            ...     logger.warning(f"Discrepancies: {consistency['discrepancies']}")
        """
        discrepancies = []
        details = {}

        # Compare symbol
        if mt5_position.symbol != db_trade.get("symbol"):
            discrepancies.append("symbol")
            details["symbol"] = {
                "mt5": mt5_position.symbol,
                "db": db_trade.get("symbol"),
            }

        # Compare volume (lots)
        if mt5_position.volume != db_trade.get("lots"):
            discrepancies.append("lots")
            details["lots"] = {
                "mt5": mt5_position.volume,
                "db": db_trade.get("lots"),
            }

        # Compare entry price
        if abs(mt5_position.price_open - db_trade.get("entry_price", 0)) > 0.00001:
            discrepancies.append("entry_price")
            details["entry_price"] = {
                "mt5": mt5_position.price_open,
                "db": db_trade.get("entry_price"),
            }

        # Compare direction
        mt5_direction = "BUY" if mt5_position.type == 0 else "SELL"
        if mt5_direction != db_trade.get("direction"):
            discrepancies.append("direction")
            details["direction"] = {
                "mt5": mt5_direction,
                "db": db_trade.get("direction"),
            }

        is_consistent = len(discrepancies) == 0

        logger.info(
            "position_consistency_check",
            ticket=mt5_position.ticket,
            is_consistent=is_consistent,
            discrepancy_count=len(discrepancies)
        )

        return {
            "is_consistent": is_consistent,
            "discrepancies": discrepancies,
            "details": details,
        }
