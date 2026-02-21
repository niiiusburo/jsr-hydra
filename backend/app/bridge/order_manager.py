"""
MT5 Order Management Module via HTTP REST Bridge

PURPOSE: Manage order submission, position closing, and modification via MT5 REST API.
Provides idempotency guarantees using Redis key-value store.
Supports dry-run mode (log orders but do not execute).

CALLED BY:
    - trading_engine
    - strategy_executor
    - risk_manager
"""

import redis.asyncio as aioredis
import hashlib
import time
from typing import Optional
from datetime import datetime

from app.bridge.connector import MT5Connector
from app.utils.logger import get_logger

logger = get_logger("bridge.order_manager")


class OrderManager:
    """
    PURPOSE: Manage MT5 orders with idempotency and dry-run support via REST API.

    Provides methods to:
    - Open positions (with idempotency via Redis)
    - Close positions by ticket
    - Query open positions
    - Close all positions

    In DRY_RUN mode: orders are logged but NOT sent to MT5. A simulated
    response is returned so the engine can continue its lifecycle.

    Attributes:
        _connector: MT5Connector instance (HTTP-based)
        _redis: Redis client for idempotency keys
        _dry_run: If True, log orders but do not execute
        _max_test_lots: Maximum lot size during testing
    """

    def __init__(
        self,
        connector: MT5Connector,
        redis_url: str,
        dry_run: bool = True,
        max_test_lots: float = 0.01,
    ):
        """
        PURPOSE: Initialize OrderManager with connector and Redis.

        Args:
            connector: MT5Connector instance
            redis_url: Redis connection URL (e.g., "redis://localhost:6379")
            dry_run: If True, simulate orders (log but don't call MT5). Default: True
            max_test_lots: Max lot size cap during testing. Default: 0.01

        Raises:
            redis.ConnectionError: If Redis connection fails (only in live mode)
        """
        self._connector = connector
        self._dry_run = dry_run
        self._max_test_lots = max_test_lots
        self._redis: Optional[aioredis.Redis] = None
        self._next_ticket = 1000  # Counter for dry-run simulated tickets
        self._simulated_positions: dict[int, dict] = {}  # ticket -> position info

        # Build async Redis client (connection is lazy — no blocking ping in __init__)
        try:
            self._redis = aioredis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_keepalive=True,
            )
            logger.info("redis_client_created", url=redis_url)
        except Exception as e:
            logger.error("redis_client_creation_failed", error=str(e))
            if not dry_run:
                raise
            # In dry-run mode, Redis is optional
            self._redis = None
            logger.warning("redis_unavailable_dry_run_mode")

        logger.info(
            "order_manager_initialized",
            dry_run=dry_run,
            max_test_lots=max_test_lots,
        )

    def _generate_idempotency_key(
        self,
        symbol: str,
        direction: str,
        timestamp_bucket: Optional[int] = None,
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
            str: SHA256 hex digest as idempotency key.
        """
        if timestamp_bucket is None:
            timestamp_bucket = int(time.time()) // 10

        key_material = f"{symbol}:{direction}:{timestamp_bucket}"
        return hashlib.sha256(key_material.encode()).hexdigest()

    async def open_position(
        self,
        symbol: str,
        direction: str,
        lots: float,
        sl: float,
        tp: float,
        comment: str = "",
    ) -> Optional[dict]:
        """
        PURPOSE: Open a new trading position with idempotency.

        Checks Redis for existing idempotency key within 10-second bucket.
        If found, returns None (prevents duplicate orders).

        In DRY_RUN mode: logs the order details and returns a simulated response
        without calling the MT5 REST API.

        In LIVE mode: calls POST /order with {symbol, direction, lots, sl, tp, comment}.
        Lots are capped to max_test_lots during testing.

        Args:
            symbol: Trading symbol (e.g., "EURUSD", "GOLD")
            direction: Trade direction - "BUY" or "SELL"
            lots: Trade size in lots (e.g., 1.0, 0.5)
            sl: Stop-loss price level
            tp: Take-profit price level
            comment: Order comment (optional)

        Returns:
            dict: Order result with keys: retcode, comment, ticket, price, volume.
            None: If duplicate order detected.

        Raises:
            ValueError: If direction not in ["BUY", "SELL"]
            ConnectionError: If MT5 REST call fails and dry_run=False
        """
        logger.info(
            "open_position_requested",
            symbol=symbol,
            direction=direction,
            lots=lots,
            sl=sl,
            tp=tp,
            dry_run=self._dry_run,
        )

        # Validate direction
        if direction.upper() not in ["BUY", "SELL"]:
            raise ValueError(f"Invalid direction: {direction}. Must be BUY or SELL.")

        # Cap lots for safety during testing
        lots = min(lots, self._max_test_lots)

        # Redis idempotency check
        idempotency_key = self._generate_idempotency_key(symbol, direction)

        if self._redis:
            try:
                if await self._redis.exists(idempotency_key):
                    logger.warning(
                        "duplicate_order_detected",
                        symbol=symbol,
                        direction=direction,
                        idempotency_key=idempotency_key,
                    )
                    return None

                # Set key with 10 second TTL
                await self._redis.setex(idempotency_key, 10, "1")

            except aioredis.RedisError as e:
                logger.error("redis_idempotency_check_failed", error=str(e))
                logger.warning("idempotency_check_skipped_due_to_redis_error")

        # ----- DRY RUN: log only, simulate response -----
        if self._dry_run:
            self._next_ticket += 1
            ticket = self._next_ticket
            simulated = {
                "retcode": 10009,
                "comment": "DRY_RUN simulated",
                "ticket": ticket,
                "price": 0.0,
                "volume": lots,
            }
            # Register the simulated position so get_open_positions() can return it
            entry_price = sl  # sl passed in; real entry unknown in dry-run, use 0
            self._simulated_positions[ticket] = {
                "ticket": ticket,
                "symbol": symbol,
                "type": 0 if direction.upper() == "BUY" else 1,
                "volume": lots,
                "price_open": 0.0,
                "sl": sl or 0,
                "tp": tp or 0,
                "profit": 0.0,
                "time": int(time.time()),
                "direction": direction.upper(),
            }
            logger.info(
                "dry_run_order_simulated",
                symbol=symbol,
                direction=direction,
                lots=lots,
                sl=sl,
                tp=tp,
                ticket=ticket,
            )
            return simulated

        # ----- LIVE: call MT5 REST API -----
        try:
            client = await self._connector._get_client()
            payload = {
                "symbol": symbol,
                "direction": direction.upper(),
                "lots": lots,
                "sl": sl,
                "tp": tp,
                "comment": comment,
            }
            resp = await client.post("/order", json=payload)
            resp.raise_for_status()
            result = resp.json()

            logger.info(
                "position_opened",
                symbol=symbol,
                direction=direction,
                lots=lots,
                retcode=result.get("retcode"),
                ticket=result.get("ticket"),
                price=result.get("price"),
            )
            return result

        except Exception as e:
            logger.error(
                "open_position_error",
                symbol=symbol,
                direction=direction,
                error=str(e),
            )
            raise ConnectionError(f"Failed to open position: {e}")

    async def close_position(self, ticket: int) -> Optional[dict]:
        """
        PURPOSE: Close an open position by ticket number.

        In DRY_RUN mode: logs and returns simulated close result.
        In LIVE mode: calls POST /close/{ticket}.

        Args:
            ticket: Position ticket number.

        Returns:
            dict: Close result with keys: retcode, comment.
            None: If the call indicates position not found.

        Raises:
            ConnectionError: If MT5 REST call fails and dry_run=False.
        """
        logger.info("close_position_requested", ticket=ticket, dry_run=self._dry_run)

        if self._dry_run:
            self.close_simulated_position(ticket)
            logger.info("dry_run_close_simulated", ticket=ticket)
            return {
                "retcode": 10009,
                "comment": "DRY_RUN close simulated",
            }

        try:
            client = await self._connector._get_client()
            resp = await client.post(f"/close/{ticket}")
            resp.raise_for_status()
            result = resp.json()

            logger.info(
                "position_closed",
                ticket=ticket,
                retcode=result.get("retcode"),
                comment=result.get("comment"),
            )
            return result

        except Exception as e:
            logger.error("close_position_error", ticket=ticket, error=str(e))
            raise ConnectionError(f"Failed to close position {ticket}: {e}")

    async def close_all_positions(self) -> list[dict]:
        """
        PURPOSE: Close all open positions.

        Retrieves all open positions via GET /positions, then closes each
        via POST /close/{ticket}. Collects and returns all close results.

        Returns:
            list[dict]: List of close results.
        """
        logger.info("close_all_positions_requested", dry_run=self._dry_run)

        positions = await self.get_open_positions()
        results = []

        for pos in positions:
            ticket = pos.get("ticket")
            if ticket is None:
                continue
            result = await self.close_position(ticket)
            if result:
                results.append(result)

        logger.info(
            "all_positions_closed",
            closed_count=len(results),
            total_positions=len(positions),
        )
        return results

    async def get_open_positions(self) -> list[dict]:
        """
        PURPOSE: Get all currently open positions.

        In DRY_RUN mode: returns the in-memory simulated position registry.
        In LIVE mode: calls GET /positions on the MT5 REST bridge.

        Returns:
            list[dict]: List of position dicts, each with keys:
                ticket, symbol, type, volume, price_open,
                sl, tp, profit, (and direction for dry-run positions).

        Raises:
            ConnectionError: If MT5 REST call fails (live mode only).
        """
        logger.info("get_open_positions_requested", dry_run=self._dry_run)

        if self._dry_run:
            positions = list(self._simulated_positions.values())
            logger.info("dry_run_positions_returned", count=len(positions))
            return positions

        try:
            client = await self._connector._get_client()
            resp = await client.get("/positions")
            resp.raise_for_status()
            positions = resp.json()

            logger.info("open_positions_retrieved", count=len(positions))
            return positions

        except Exception as e:
            logger.error("get_open_positions_error", error=str(e))
            raise ConnectionError(f"Failed to get open positions: {e}")

    def close_simulated_position(self, ticket: int) -> Optional[dict]:
        """
        PURPOSE: Remove a simulated position from the in-memory registry.

        Called by the engine when a DRY_RUN position's SL or TP has been hit,
        so that `get_open_positions()` no longer returns it.

        Args:
            ticket: Simulated position ticket number.

        Returns:
            dict: The removed position info, or None if ticket not found.
        """
        removed = self._simulated_positions.pop(ticket, None)
        if removed:
            logger.info("simulated_position_closed", ticket=ticket)
        else:
            logger.warning("simulated_position_not_found_for_close", ticket=ticket)
        return removed

    async def get_position_by_ticket(self, ticket: int) -> Optional[dict]:
        """
        PURPOSE: Get single position by ticket number.

        Retrieves all positions and filters by ticket.

        Args:
            ticket: Position ticket number.

        Returns:
            dict: Position dict, or None if not found.
        """
        logger.info("get_position_by_ticket_requested", ticket=ticket)

        positions = await self.get_open_positions()
        for pos in positions:
            if pos.get("ticket") == ticket:
                return pos

        logger.warning("position_not_found", ticket=ticket)
        return None
