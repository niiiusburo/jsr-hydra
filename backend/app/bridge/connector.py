"""
MT5 Connection Management via HTTP REST Bridge

PURPOSE: Manage HTTP connection to MT5 REST bridge server running in jsr-mt5 container.
Uses httpx async client to communicate with the MT5 REST API.

CALLED BY:
    - engine/orchestrator.py
    - data_feed.py
    - order_manager.py
    - account_info.py
"""

import httpx
from typing import Optional

from app.config.constants import EventType
from app.utils.logger import get_logger
from app.utils.decorators import CircuitBreaker, retry

logger = get_logger("bridge.connector")


class MT5Connector:
    """
    PURPOSE: Manage HTTP connection to MT5 REST bridge server.

    Handles health checks, connection state, and provides methods
    to call the MT5 REST API endpoints. Uses circuit breaker pattern
    for resilience and httpx async client for HTTP calls.

    Attributes:
        _base_url: MT5 REST bridge base URL
        _connected: Connection state flag
        _circuit: CircuitBreaker for resilience
        _client: httpx.AsyncClient instance
    """

    def __init__(self, base_url: str = "http://jsr-mt5:18812"):
        """
        PURPOSE: Initialize MT5Connector with REST bridge URL.

        Args:
            base_url: MT5 REST bridge base URL (e.g., "http://jsr-mt5:18812")
        """
        self._base_url = base_url.rstrip("/")
        self._connected = False
        self._circuit = CircuitBreaker(failure_threshold=5, reset_timeout=60.0)
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """
        PURPOSE: Get or create the httpx async client.

        Returns:
            httpx.AsyncClient: Reusable HTTP client instance.
        """
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=httpx.Timeout(10.0, connect=5.0),
            )
        return self._client

    @retry(max_retries=3, delay=2.0, backoff=2.0)
    async def connect(self) -> bool:
        """
        PURPOSE: Check MT5 REST bridge health and mark as connected.

        Sends GET /health to the MT5 REST bridge. If healthy,
        sets _connected = True. Uses retry decorator with
        exponential backoff (2s -> 4s -> 8s).

        Returns:
            bool: True if health check succeeds.

        Raises:
            ConnectionError: If health check fails.
        """
        try:
            client = await self._get_client()
            resp = await client.get("/health")
            resp.raise_for_status()

            self._connected = True
            logger.info(
                "mt5_connected",
                base_url=self._base_url,
            )

            # Publish MT5_CONNECTED event (fire-and-forget)
            try:
                from app.events.bus import get_event_bus
                bus = get_event_bus()
                await bus.publish(
                    event_type=EventType.MT5_CONNECTED.value,
                    data={"base_url": self._base_url},
                    source="bridge.connector",
                    severity="INFO",
                )
            except Exception:
                logger.warning("event_publish_failed_mt5_connected")

            return True

        except Exception as e:
            logger.error(
                "mt5_connection_error",
                base_url=self._base_url,
                error=str(e),
            )
            raise ConnectionError(f"MT5 REST bridge health check failed: {e}")

    async def disconnect(self) -> None:
        """
        PURPOSE: Mark connector as disconnected and close HTTP client.

        No-op on the server side (stateless REST). Closes the local
        httpx client and sets _connected = False.
        """
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

        self._connected = False
        logger.info("mt5_disconnected")

        # Publish MT5_DISCONNECTED event (fire-and-forget)
        try:
            from app.events.bus import get_event_bus
            bus = get_event_bus()
            await bus.publish(
                event_type=EventType.MT5_DISCONNECTED.value,
                data={"base_url": self._base_url},
                source="bridge.connector",
                severity="WARNING",
            )
        except Exception:
            logger.warning("event_publish_failed_mt5_disconnected")

    @property
    def is_connected(self) -> bool:
        """
        PURPOSE: Check if MT5 REST bridge connection is considered active.

        Returns:
            bool: True if last health check succeeded.
        """
        return self._connected

    async def get_account_info(self) -> dict:
        """
        PURPOSE: Get MT5 account information via REST API.

        Retrieves account info via circuit-breaker-protected GET /account.

        Returns:
            dict: Account info with keys: login, server, balance, equity,
                  margin, free_margin, margin_level, profit, currency, leverage.

        Raises:
            ConnectionError: If account info retrieval fails.
        """
        async def _fetch():
            client = await self._get_client()
            resp = await client.get("/account")
            resp.raise_for_status()
            return resp.json()

        try:
            info = await self._circuit(_fetch)()

            logger.info(
                "mt5_account_info_retrieved",
                login=info.get("login"),
                balance=info.get("balance"),
                equity=info.get("equity"),
            )
            return info

        except Exception as e:
            logger.error("mt5_account_info_error", error=str(e))
            raise ConnectionError(f"Failed to get account info: {e}")

    async def get_symbols(self) -> list[dict]:
        """
        PURPOSE: Get list of available trading symbols from MT5.

        Returns:
            list[dict]: Symbol info dicts with keys: name, point, digits,
                        spread, volume_min, volume_max, volume_step.

        Raises:
            ConnectionError: If request fails.
        """
        try:
            client = await self._get_client()
            resp = await client.get("/symbols")
            resp.raise_for_status()
            symbols = resp.json()
            logger.info("mt5_symbols_retrieved", count=len(symbols))
            return symbols
        except Exception as e:
            logger.error("mt5_get_symbols_error", error=str(e))
            raise ConnectionError(f"Failed to get symbols: {e}")

    @property
    def base_url(self) -> str:
        """Return the configured base URL."""
        return self._base_url
