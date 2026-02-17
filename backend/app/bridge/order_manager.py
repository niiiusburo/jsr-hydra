"""
MT5 Order Management Module

PURPOSE: Manage order submission, position closing, and modification via MT5.
Provides idempotency guarantees using Redis key-value store.
Supports dry-run simulation mode.

CALLED BY:
    - trading_engine
    - strategy_executor
    - risk_manager
"""

import redis
import hashlib
import time
import uuid
from typing import Optional, Any
from datetime import datetime, timedelta

from app.bridge.connector import MT5Connector
from app.utils.logger import get_logger

logger = get_logger("bridge.order_manager")


class OrderManager:
    """
    PURPOSE: Manage MT5 orders with idempotency and dry-run support.

    Provides methods to:
    - Open positions (with idempotency via Redis)
    - Close positions by ticket
    - Modify stop-loss and take-profit
    - Query open positions
    - Close all positions

    Attributes:
        _connector: MT5Connector instance
        _redis: Redis client for idempotency keys
        _dry_run: Enable mock order simulation if True
        _next_ticket: Counter for dry-run tickets
        _open_positions: Dict of simulated positions (dry-run mode)
    """

    def __init__(
        self,
        connector: MT5Connector,
        redis_url: str,
        dry_run: bool = True
    ):
        """
        PURPOSE: Initialize OrderManager with connector and Redis.

        Args:
            connector: MT5Connector instance
            redis_url: Redis connection URL (e.g., "redis://localhost:6379")
            dry_run: If True, simulate orders in memory. Default: True

        Raises:
            redis.ConnectionError: If Redis connection fails (only in live mode)

        Example:
            >>> om = OrderManager(connector, "redis://localhost:6379", dry_run=True)
        """
        self._connector = connector
        self._dry_run = dry_run
        self._redis: Optional[redis.Redis] = None
        self._next_ticket = 1000
        self._open_positions = {}

        if not dry_run:
            try:
                self._redis = redis.from_url(
                    redis_url,
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_keepalive=True,
                )
                # Test connection
                self._redis.ping()
                logger.info("redis_connected", url=redis_url)
            except redis.ConnectionError as e:
                logger.error("redis_connection_failed", error=str(e))
                raise

        logger.info("order_manager_initialized", dry_run=dry_run)

    def _generate_idempotency_key(
        self,
        symbol: str,
        direction: str,
        timestamp_bucket: Optional[int] = None
    ) -> str:
        """
        PURPOSE: Generate SHA256 idempotency key from symbol, direction, time bucket.

        Idempotency key prevents duplicate orders within a 10-second window.
        Key format: SHA256(f"{symbol}:{direction}:{ts//10}")

        Args:
            symbol: Trading symbol (e.g., "EURUSD")
            direction: Trade direction ("BUY" or "SELL")
            timestamp_bucket: Unix timestamp bucket (10-second intervals).
                             If None, uses current time.

        Returns:
            str: SHA256 hex digest as idempotency key

        Example:
            >>> key = om._generate_idempotency_key("EURUSD", "BUY", 1708000000)
            >>> len(key)
            64
        """
        if timestamp_bucket is None:
            timestamp_bucket = int(time.time()) // 10

        key_material = f"{symbol}:{direction}:{timestamp_bucket}"
        key = hashlib.sha256(key_material.encode()).hexdigest()

        return key

    def open_position(
        self,
        symbol: str,
        direction: str,
        lots: float,
        sl: float,
        tp: float,
        comment: str = ""
    ) -> Optional[dict]:
        """
        PURPOSE: Open a new trading position with idempotency.

        Checks Redis for existing idempotency key within 10-second bucket.
        If found, logs warning and returns None (prevents duplicate orders).
        Otherwise, submits order to MT5 and stores idempotency key with 10s TTL.

        In dry-run mode, simulates order execution with fake ticket.

        Args:
            symbol: Trading symbol (e.g., "EURUSD", "GOLD")
            direction: Trade direction - "BUY" or "SELL"
            lots: Trade size in lots (e.g., 1.0, 0.5)
            sl: Stop-loss price level
            tp: Take-profit price level
            comment: Order comment (optional, max 31 chars)

        Returns:
            dict: Order result with keys:
                - ticket: int - Order ticket number
                - price: float - Execution price
                - lots: float - Trade size
                - time: datetime - Execution time
            None: If order is duplicate (idempotency check failed)

        Raises:
            ValueError: If direction not in ["BUY", "SELL"]
            ConnectionError: If MT5 connection fails and dry_run=False

        Example:
            >>> result = om.open_position("EURUSD", "BUY", 1.0, 1.0700, 1.0900)
            >>> if result:
            ...     print(f"Ticket: {result['ticket']}")
            ... else:
            ...     print("Duplicate order detected")
        """
        logger.info(
            "open_position_requested",
            symbol=symbol,
            direction=direction,
            lots=lots,
            sl=sl,
            tp=tp,
            dry_run=self._dry_run
        )

        # Validate direction
        if direction.upper() not in ["BUY", "SELL"]:
            raise ValueError(f"Invalid direction: {direction}. Must be BUY or SELL.")

        # Check idempotency (skip in dry-run if no Redis)
        idempotency_key = self._generate_idempotency_key(symbol, direction)

        if not self._dry_run and self._redis:
            try:
                # Check if key exists
                if self._redis.exists(idempotency_key):
                    logger.warning(
                        "duplicate_order_detected",
                        symbol=symbol,
                        direction=direction,
                        idempotency_key=idempotency_key
                    )
                    return None

                # Set key with 10 second TTL
                self._redis.setex(idempotency_key, 10, "1")

            except redis.RedisError as e:
                logger.error(
                    "redis_idempotency_check_failed",
                    error=str(e)
                )
                # Continue anyway, but log warning
                logger.warning("idempotency_check_skipped_due_to_redis_error")

        if self._dry_run:
            return self._simulate_open_position(
                symbol=symbol,
                direction=direction,
                lots=lots,
                sl=sl,
                tp=tp,
                comment=comment
            )

        # Live order submission
        try:
            if not self._connector.is_connected():
                raise ConnectionError("MT5 not connected. Call connector.connect() first.")

            # Prepare request structure for MT5
            # MT5 order types: 0=BUY, 1=SELL, 2=BUYLIMIT, 3=SELLLIMIT, 4=BUYSTOP, 5=SELLSTOP
            order_type = 0 if direction.upper() == "BUY" else 1

            # Get current tick to determine entry price
            tick = self._connector.mt5.symbol_info_tick(symbol)
            if tick is None:
                raise ConnectionError(f"Cannot get tick for {symbol}")

            entry_price = tick.ask if direction.upper() == "BUY" else tick.bid

            # Build request dict
            request = {
                "action": 1,  # TRADE_ACTION_DEAL
                "symbol": symbol,
                "volume": lots,
                "type": order_type,
                "price": entry_price,
                "sl": sl,
                "tp": tp,
                "comment": comment,
                "type_time": 1,  # ORDER_TIME_GTC (Good Till Cancelled)
                "type_filling": 1,  # ORDER_FILLING_IOC (Immediate or Cancel)
            }

            # Submit order
            result = self._connector.mt5.order_send(request)

            if result is None or result.retcode != 10009:  # TRADE_RETCODE_DONE
                error_msg = f"Order send failed: {self._connector.mt5.last_error()}"
                logger.error(
                    "mt5_order_send_failed",
                    symbol=symbol,
                    direction=direction,
                    error=error_msg
                )
                raise ConnectionError(error_msg)

            order_dict = {
                "ticket": result.order,
                "price": entry_price,
                "lots": lots,
                "time": datetime.utcnow(),
            }

            logger.info(
                "position_opened",
                ticket=result.order,
                symbol=symbol,
                direction=direction,
                lots=lots,
                price=entry_price
            )
            return order_dict

        except Exception as e:
            logger.error(
                "open_position_error",
                symbol=symbol,
                direction=direction,
                error=str(e)
            )
            raise

    def _simulate_open_position(
        self,
        symbol: str,
        direction: str,
        lots: float,
        sl: float,
        tp: float,
        comment: str = ""
    ) -> dict:
        """
        PURPOSE: Simulate position opening in dry-run mode.

        Creates fake position with simulated ticket and price.
        Stores in _open_positions dict for tracking.

        Args:
            symbol: Symbol
            direction: BUY or SELL
            lots: Lot size
            sl: Stop loss
            tp: Take profit
            comment: Order comment

        Returns:
            dict: Simulated order result
        """
        ticket = self._next_ticket
        self._next_ticket += 1

        # Mock price (uses simple heuristic)
        import numpy as np
        np.random.seed(hash(symbol + str(time.time())) % 2**32)
        base_prices = {
            "EURUSD": 1.0800, "GBPUSD": 1.2700, "USDJPY": 150.0,
            "AUDUSD": 0.6500, "USDCAD": 1.3500, "NZDUSD": 0.5900,
            "EURGBP": 0.8500, "EURJPY": 162.0, "GBPJPY": 190.0,
            "GOLD": 2050.0, "WTI": 75.0, "DXUSD": 104.0,
        }
        base_price = base_prices.get(symbol, 100.0)
        price = base_price * (1 + np.random.normal(0, 0.001))

        position = {
            "ticket": ticket,
            "symbol": symbol,
            "direction": direction,
            "lots": lots,
            "entry_price": price,
            "sl": sl,
            "tp": tp,
            "comment": comment,
            "opened_at": datetime.utcnow(),
            "status": "OPEN",
        }

        self._open_positions[ticket] = position

        logger.info(
            "simulated_position_opened",
            ticket=ticket,
            symbol=symbol,
            direction=direction,
            lots=lots,
            price=price
        )

        return {
            "ticket": ticket,
            "price": price,
            "lots": lots,
            "time": datetime.utcnow(),
        }

    def close_position(self, ticket: int) -> Optional[dict]:
        """
        PURPOSE: Close an open position by ticket number.

        Submits closing order to MT5 for the specified ticket.
        In dry-run mode, marks position as closed in memory.

        Args:
            ticket: Position ticket number

        Returns:
            dict: Close result with keys:
                - ticket: int - Position ticket
                - close_price: float - Close price
                - profit: float - Realized P&L
                - time: datetime - Close time
            None: If position not found

        Raises:
            ConnectionError: If MT5 connection fails and dry_run=False

        Example:
            >>> result = om.close_position(1001)
            >>> if result:
            ...     print(f"Closed at {result['close_price']}, Profit: {result['profit']}")
        """
        logger.info("close_position_requested", ticket=ticket, dry_run=self._dry_run)

        if self._dry_run:
            return self._simulate_close_position(ticket)

        try:
            if not self._connector.is_connected():
                raise ConnectionError("MT5 not connected")

            # Get position info first
            positions = self._connector.mt5.positions_get()
            if positions is None:
                logger.warning("no_positions_found")
                return None

            position = None
            for pos in positions:
                if pos.ticket == ticket:
                    position = pos
                    break

            if position is None:
                logger.warning("position_not_found", ticket=ticket)
                return None

            # Get current tick for close price
            tick = self._connector.mt5.symbol_info_tick(position.symbol)
            if tick is None:
                raise ConnectionError(f"Cannot get tick for {position.symbol}")

            close_price = tick.bid if position.type == 0 else tick.ask

            # Build close request
            close_request = {
                "action": 1,  # TRADE_ACTION_DEAL
                "symbol": position.symbol,
                "volume": position.volume,
                "type": 1 if position.type == 0 else 0,  # Opposite of entry type
                "position": ticket,
                "price": close_price,
                "type_time": 1,
                "type_filling": 1,
            }

            # Submit close order
            result = self._connector.mt5.order_send(close_request)

            if result is None or result.retcode != 10009:
                error_msg = f"Close order failed: {self._connector.mt5.last_error()}"
                logger.error("mt5_close_failed", ticket=ticket, error=error_msg)
                raise ConnectionError(error_msg)

            # Calculate profit
            if position.type == 0:  # BUY
                profit = (close_price - position.price_open) * position.volume
            else:  # SELL
                profit = (position.price_open - close_price) * position.volume

            close_result = {
                "ticket": ticket,
                "close_price": close_price,
                "profit": profit,
                "time": datetime.utcnow(),
            }

            logger.info(
                "position_closed",
                ticket=ticket,
                close_price=close_price,
                profit=profit
            )
            return close_result

        except Exception as e:
            logger.error(
                "close_position_error",
                ticket=ticket,
                error=str(e)
            )
            raise

    def _simulate_close_position(self, ticket: int) -> Optional[dict]:
        """
        PURPOSE: Simulate position closing in dry-run mode.

        Args:
            ticket: Position ticket

        Returns:
            dict: Simulated close result, or None if not found
        """
        if ticket not in self._open_positions:
            logger.warning("simulated_position_not_found", ticket=ticket)
            return None

        position = self._open_positions[ticket]

        # Mock close price with small slippage
        import numpy as np
        np.random.seed(hash(str(ticket) + str(time.time())) % 2**32)
        close_price = position["entry_price"] * (1 + np.random.normal(0, 0.002))

        if position["direction"].upper() == "BUY":
            profit = (close_price - position["entry_price"]) * position["lots"]
        else:
            profit = (position["entry_price"] - close_price) * position["lots"]

        position["status"] = "CLOSED"
        position["close_price"] = close_price
        position["profit"] = profit
        position["closed_at"] = datetime.utcnow()

        logger.info(
            "simulated_position_closed",
            ticket=ticket,
            close_price=close_price,
            profit=profit
        )

        return {
            "ticket": ticket,
            "close_price": close_price,
            "profit": profit,
            "time": datetime.utcnow(),
        }

    def modify_position(
        self,
        ticket: int,
        sl: Optional[float] = None,
        tp: Optional[float] = None
    ) -> Optional[dict]:
        """
        PURPOSE: Modify stop-loss and/or take-profit for open position.

        Updates SL/TP levels for the specified position ticket.
        In dry-run mode, updates simulated position.

        Args:
            ticket: Position ticket number
            sl: New stop-loss price (optional)
            tp: New take-profit price (optional)

        Returns:
            dict: Update result with keys:
                - ticket: int - Position ticket
                - sl: float - New stop-loss
                - tp: float - New take-profit
                - time: datetime - Update time
            None: If position not found

        Raises:
            ValueError: If both sl and tp are None
            ConnectionError: If MT5 connection fails and dry_run=False

        Example:
            >>> om.modify_position(1001, sl=1.0700, tp=1.0900)
        """
        if sl is None and tp is None:
            raise ValueError("At least one of sl or tp must be provided")

        logger.info(
            "modify_position_requested",
            ticket=ticket,
            sl=sl,
            tp=tp,
            dry_run=self._dry_run
        )

        if self._dry_run:
            return self._simulate_modify_position(ticket, sl, tp)

        try:
            if not self._connector.is_connected():
                raise ConnectionError("MT5 not connected")

            # Get position
            positions = self._connector.mt5.positions_get()
            if positions is None:
                logger.warning("no_positions_found")
                return None

            position = None
            for pos in positions:
                if pos.ticket == ticket:
                    position = pos
                    break

            if position is None:
                logger.warning("position_not_found", ticket=ticket)
                return None

            # Build modify request
            modify_request = {
                "action": 2,  # TRADE_ACTION_MODIFY
                "position": ticket,
                "type_time": 1,
                "type_filling": 1,
            }

            if sl is not None:
                modify_request["sl"] = sl

            if tp is not None:
                modify_request["tp"] = tp

            # Submit modify order
            result = self._connector.mt5.order_send(modify_request)

            if result is None or result.retcode != 10009:
                error_msg = f"Modify failed: {self._connector.mt5.last_error()}"
                logger.error("mt5_modify_failed", ticket=ticket, error=error_msg)
                raise ConnectionError(error_msg)

            modify_result = {
                "ticket": ticket,
                "sl": sl or position.sl,
                "tp": tp or position.tp,
                "time": datetime.utcnow(),
            }

            logger.info(
                "position_modified",
                ticket=ticket,
                sl=sl,
                tp=tp
            )
            return modify_result

        except Exception as e:
            logger.error(
                "modify_position_error",
                ticket=ticket,
                error=str(e)
            )
            raise

    def _simulate_modify_position(
        self,
        ticket: int,
        sl: Optional[float],
        tp: Optional[float]
    ) -> Optional[dict]:
        """
        PURPOSE: Simulate position modification in dry-run mode.

        Args:
            ticket: Position ticket
            sl: New SL (optional)
            tp: New TP (optional)

        Returns:
            dict: Simulated modify result, or None if not found
        """
        if ticket not in self._open_positions:
            logger.warning("simulated_position_not_found", ticket=ticket)
            return None

        position = self._open_positions[ticket]

        if sl is not None:
            position["sl"] = sl

        if tp is not None:
            position["tp"] = tp

        logger.info(
            "simulated_position_modified",
            ticket=ticket,
            sl=sl,
            tp=tp
        )

        return {
            "ticket": ticket,
            "sl": sl or position["sl"],
            "tp": tp or position["tp"],
            "time": datetime.utcnow(),
        }

    def close_all_positions(self) -> list[dict]:
        """
        PURPOSE: Close all open positions.

        Retrieves all open positions and closes each one.
        Returns list of close results.

        Returns:
            list[dict]: List of close results (see close_position for dict format)

        Raises:
            ConnectionError: If MT5 connection fails and dry_run=False

        Example:
            >>> results = om.close_all_positions()
            >>> print(f"Closed {len(results)} positions")
        """
        logger.info("close_all_positions_requested", dry_run=self._dry_run)

        positions = self.get_open_positions()
        results = []

        for pos in positions:
            ticket = pos["ticket"]
            result = self.close_position(ticket)
            if result:
                results.append(result)

        logger.info(
            "all_positions_closed",
            closed_count=len(results),
            total_positions=len(positions)
        )
        return results

    def get_open_positions(self) -> list[dict]:
        """
        PURPOSE: Get all currently open positions.

        Queries MT5 for all open positions and returns as list of dicts.
        In dry-run mode, returns simulated positions with OPEN status.

        Returns:
            list[dict]: List of position dicts, each with:
                - ticket: int - Position ticket
                - symbol: str - Trading symbol
                - direction: str - BUY or SELL
                - lots: float - Position size
                - entry_price: float - Entry price
                - sl: float - Stop loss
                - tp: float - Take profit
                - current_profit: float - Current P&L
                - open_time: datetime - Entry time

        Raises:
            ConnectionError: If MT5 connection fails and dry_run=False

        Example:
            >>> positions = om.get_open_positions()
            >>> print(f"{len(positions)} open positions")
        """
        logger.info("get_open_positions_requested", dry_run=self._dry_run)

        if self._dry_run:
            positions = []
            for ticket, pos in self._open_positions.items():
                if pos["status"] == "OPEN":
                    positions.append({
                        "ticket": ticket,
                        "symbol": pos["symbol"],
                        "direction": pos["direction"],
                        "lots": pos["lots"],
                        "entry_price": pos["entry_price"],
                        "sl": pos["sl"],
                        "tp": pos["tp"],
                        "current_profit": 0.0,
                        "open_time": pos["opened_at"],
                    })
            logger.info(
                "simulated_positions_retrieved",
                count=len(positions)
            )
            return positions

        try:
            if not self._connector.is_connected():
                raise ConnectionError("MT5 not connected")

            mt5_positions = self._connector.mt5.positions_get()

            if mt5_positions is None or len(mt5_positions) == 0:
                logger.info("no_open_positions")
                return []

            positions = []
            for mt5_pos in mt5_positions:
                pos_dict = {
                    "ticket": mt5_pos.ticket,
                    "symbol": mt5_pos.symbol,
                    "direction": "BUY" if mt5_pos.type == 0 else "SELL",
                    "lots": mt5_pos.volume,
                    "entry_price": mt5_pos.price_open,
                    "sl": mt5_pos.sl,
                    "tp": mt5_pos.tp,
                    "current_profit": mt5_pos.profit,
                    "open_time": datetime.fromtimestamp(mt5_pos.time),
                }
                positions.append(pos_dict)

            logger.info(
                "open_positions_retrieved",
                count=len(positions)
            )
            return positions

        except Exception as e:
            logger.error(
                "get_open_positions_error",
                error=str(e)
            )
            raise

    def get_position_by_ticket(self, ticket: int) -> Optional[dict]:
        """
        PURPOSE: Get single position by ticket number.

        Retrieves position details for specified ticket.
        Returns None if position not found.

        Args:
            ticket: Position ticket number

        Returns:
            dict: Position dict (see get_open_positions for format), or None

        Raises:
            ConnectionError: If MT5 connection fails and dry_run=False

        Example:
            >>> pos = om.get_position_by_ticket(1001)
            >>> if pos:
            ...     print(f"Symbol: {pos['symbol']}, Profit: {pos['current_profit']}")
        """
        logger.info(
            "get_position_by_ticket_requested",
            ticket=ticket,
            dry_run=self._dry_run
        )

        if self._dry_run:
            if ticket in self._open_positions:
                pos = self._open_positions[ticket]
                if pos["status"] == "OPEN":
                    return {
                        "ticket": ticket,
                        "symbol": pos["symbol"],
                        "direction": pos["direction"],
                        "lots": pos["lots"],
                        "entry_price": pos["entry_price"],
                        "sl": pos["sl"],
                        "tp": pos["tp"],
                        "current_profit": 0.0,
                        "open_time": pos["opened_at"],
                    }
            return None

        try:
            if not self._connector.is_connected():
                raise ConnectionError("MT5 not connected")

            positions = self._connector.mt5.positions_get(ticket=ticket)

            if positions is None or len(positions) == 0:
                logger.warning("position_not_found", ticket=ticket)
                return None

            mt5_pos = positions[0]
            pos_dict = {
                "ticket": mt5_pos.ticket,
                "symbol": mt5_pos.symbol,
                "direction": "BUY" if mt5_pos.type == 0 else "SELL",
                "lots": mt5_pos.volume,
                "entry_price": mt5_pos.price_open,
                "sl": mt5_pos.sl,
                "tp": mt5_pos.tp,
                "current_profit": mt5_pos.profit,
                "open_time": datetime.fromtimestamp(mt5_pos.time),
            }

            logger.info(
                "position_retrieved",
                ticket=ticket,
                symbol=mt5_pos.symbol
            )
            return pos_dict

        except Exception as e:
            logger.error(
                "get_position_by_ticket_error",
                ticket=ticket,
                error=str(e)
            )
            raise
