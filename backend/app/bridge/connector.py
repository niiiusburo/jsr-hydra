"""
MT5 Connection Management via mt5linux RPyC Bridge

PURPOSE: Manage RPyC connection to MT5 Docker container running under Wine.
Uses mt5linux library which provides the same API as MetaTrader5 but via RPyC.

CALLED BY:
    - engine/orchestrator.py
    - data_feed.py
    - order_manager.py
    - account_info.py
"""

try:
    from mt5linux import MetaTrader5
except ImportError:
    # Fallback for testing without mt5linux installed
    MetaTrader5 = None

from typing import Optional, Any
from app.utils.logger import get_logger
from app.utils.decorators import CircuitBreaker, retry

logger = get_logger("bridge.connector")


class MT5Connector:
    """
    PURPOSE: Manage RPyC connection to MT5 Docker container.

    Handles initialization, login, connection state, and cleanup.
    Provides circuit breaker pattern for resilience.
    Thread-safe singleton connection per instance.

    Attributes:
        _host: MT5 Docker RPyC server hostname
        _port: MT5 Docker RPyC server port
        _login: MT5 account login number
        _password: MT5 account password
        _server: MT5 server name
        _mt5: MetaTrader5 instance (from mt5linux)
        _connected: Connection state flag
        _circuit: CircuitBreaker for resilience
    """

    def __init__(
        self,
        host: str,
        port: int,
        login: int,
        password: str,
        server: str
    ):
        """
        PURPOSE: Initialize MT5Connector with connection parameters.

        Args:
            host: MT5 Docker RPyC server hostname (e.g., "localhost")
            port: MT5 Docker RPyC server port (e.g., 18861)
            login: MT5 account login number
            password: MT5 account password
            server: MT5 server name (e.g., "VolatilityUltra-Demo")
        """
        self._host = host
        self._port = port
        self._login = login
        self._password = password
        self._server = server
        self._mt5: Optional[Any] = None
        self._connected = False
        self._circuit = CircuitBreaker(failure_threshold=5, reset_timeout=60.0)

    @retry(max_retries=3, delay=2.0, backoff=2.0)
    def connect(self) -> bool:
        """
        PURPOSE: Initialize RPyC connection to MT5 container and login.

        Attempts to connect via mt5linux RPyC bridge, initialize MT5,
        and login with provided credentials. Uses retry decorator with
        exponential backoff (2s -> 4s -> 8s).

        Returns:
            bool: True if connection and login successful

        Raises:
            ConnectionError: If MT5 initialization or login fails
            ImportError: If mt5linux not available

        Example:
            >>> connector = MT5Connector("localhost", 18861, 12345, "pass", "Demo")
            >>> connector.connect()
            True
        """
        if MetaTrader5 is None:
            raise ImportError(
                "mt5linux not installed. Install with: pip install mt5linux"
            )

        try:
            # Create RPyC connection to MT5
            self._mt5 = MetaTrader5(host=self._host, port=self._port)

            # Initialize MT5
            if not self._mt5.initialize():
                error_msg = f"MT5 initialize failed: {self._mt5.last_error()}"
                logger.error("mt5_init_failed", error=error_msg)
                raise ConnectionError(error_msg)

            # Login
            if not self._mt5.login(
                login=self._login,
                password=self._password,
                server=self._server
            ):
                error_msg = f"MT5 login failed: {self._mt5.last_error()}"
                logger.error("mt5_login_failed", error=error_msg, login=self._login)
                raise ConnectionError(error_msg)

            self._connected = True
            logger.info(
                "mt5_connected",
                host=self._host,
                port=self._port,
                login=self._login
            )
            return True

        except Exception as e:
            logger.error(
                "mt5_connection_error",
                host=self._host,
                port=self._port,
                error=str(e)
            )
            raise

    def disconnect(self) -> None:
        """
        PURPOSE: Gracefully shutdown MT5 connection.

        Calls shutdown() on MT5 instance if available.
        Silently ignores errors during shutdown.
        Sets _connected flag to False.

        Returns:
            None

        Example:
            >>> connector.disconnect()
        """
        if self._mt5:
            try:
                self._mt5.shutdown()
            except Exception as e:
                logger.warning(
                    "mt5_shutdown_error",
                    error=str(e)
                )

        self._connected = False
        logger.info("mt5_disconnected")

    def is_connected(self) -> bool:
        """
        PURPOSE: Check if MT5 connection is active.

        Returns:
            bool: True if connected and _mt5 instance exists, False otherwise

        Example:
            >>> if connector.is_connected():
            ...     data = connector.mt5.symbol_info_tick("EURUSD")
        """
        return self._connected and self._mt5 is not None

    @property
    def mt5(self) -> Any:
        """
        PURPOSE: Get the MT5 instance for direct API calls.

        Checks connection state before returning. Use this property
        to access underlying mt5linux MetaTrader5 API.

        Returns:
            MetaTrader5: Connected mt5linux instance

        Raises:
            ConnectionError: If not connected

        Example:
            >>> ticks = connector.mt5.copy_rates_from_pos("EURUSD", 0, 200)
        """
        if not self.is_connected():
            raise ConnectionError("MT5 not connected. Call connect() first.")
        return self._mt5

    def get_account_info(self) -> dict:
        """
        PURPOSE: Get MT5 account information.

        Retrieves account info via circuit breaker protected call.
        Converts mt5linux AccountInfo namedtuple to dict.

        Returns:
            dict: Account info dict with keys:
                - login: int - Account login number
                - server: str - Server name
                - name: str - Account owner name
                - currency: str - Account base currency
                - balance: float - Account balance
                - equity: float - Current equity
                - margin: float - Used margin
                - free_margin: float - Free margin available
                - margin_level: float - Margin level percentage

        Raises:
            ConnectionError: If account info retrieval fails

        Example:
            >>> info = connector.get_account_info()
            >>> print(info['balance'])
            10000.0
        """
        try:
            # Use circuit breaker for resilience
            info = self._circuit(lambda: self._mt5.account_info())()

            if info is None:
                error_msg = "account_info() returned None"
                logger.error("mt5_account_info_failed", error=error_msg)
                raise ConnectionError(error_msg)

            logger.info(
                "mt5_account_info_retrieved",
                login=info.login,
                balance=info.balance,
                equity=info.equity
            )
            return info._asdict()

        except Exception as e:
            logger.error(
                "mt5_account_info_error",
                error=str(e)
            )
            raise ConnectionError(f"Failed to get account info: {str(e)}")
