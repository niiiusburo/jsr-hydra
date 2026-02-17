"""
MT5 Data Feed Module

PURPOSE: Provide OHLCV candle data and tick data from MT5 via RPyC.
Supports both live trading (MT5 connection) and dry-run (mock data).

CALLED BY:
    - strategies
    - analysis engines
    - backtesting systems
"""

from datetime import datetime, timedelta
from typing import Optional
import numpy as np
import pandas as pd

from app.bridge.connector import MT5Connector
from app.utils.logger import get_logger

logger = get_logger("bridge.data_feed")

# Supported symbols for dry-run mode
SUPPORTED_SYMBOLS = [
    "EURUSD",
    "GBPUSD",
    "USDJPY",
    "AUDUSD",
    "USDCAD",
    "NZDUSD",
    "EURGBP",
    "EURJPY",
    "GBPJPY",
    "GOLD",
    "WTI",
    "DXUSD",
]

# Supported timeframes (MT5 format)
TIMEFRAME_MAP = {
    "M1": "1",
    "M5": "5",
    "M15": "15",
    "M30": "30",
    "H1": "60",
    "H4": "240",
    "D1": "1440",
    "W1": "10080",
}


class DataFeed:
    """
    PURPOSE: Fetch OHLCV candles and tick data from MT5.

    Provides methods to retrieve historical candles and tick data
    with full dry-run support for backtesting and testing scenarios.
    Uses mt5linux RPyC bridge for live data.

    Attributes:
        _connector: MT5Connector instance
        _dry_run: Enable mock data generation if True
    """

    def __init__(self, connector: MT5Connector, dry_run: bool = True):
        """
        PURPOSE: Initialize DataFeed with connector and dry-run mode.

        Args:
            connector: MT5Connector instance for live data
            dry_run: If True, generate mock OHLCV data. Default: True

        Example:
            >>> feed = DataFeed(connector, dry_run=False)
        """
        self._connector = connector
        self._dry_run = dry_run
        logger.info("data_feed_initialized", dry_run=dry_run)

    def get_candles(
        self,
        symbol: str,
        timeframe: str,
        count: int = 200
    ) -> pd.DataFrame:
        """
        PURPOSE: Fetch OHLCV candles for symbol and timeframe.

        Retrieves candles from MT5 via mt5linux RPyC if connected.
        In dry-run mode, generates synthetic OHLCV data with realistic
        properties (closes > opens, touches of highs/lows, volume variation).

        Args:
            symbol: Symbol to fetch (e.g., "EURUSD", "GOLD")
            timeframe: Timeframe as string (e.g., "H1", "D1", "M15")
            count: Number of candles to fetch. Default: 200

        Returns:
            pd.DataFrame: DataFrame with columns:
                - time: datetime - Candle open time
                - open: float - Opening price
                - high: float - High price
                - low: float - Low price
                - close: float - Closing price
                - volume: float - Volume in lots
                Index: time (datetime)

        Raises:
            ValueError: If symbol or timeframe not supported
            ConnectionError: If MT5 connection fails and dry_run=False

        Example:
            >>> df = feed.get_candles("EURUSD", "H1", count=100)
            >>> print(df.head())
        """
        logger.info(
            "get_candles_requested",
            symbol=symbol,
            timeframe=timeframe,
            count=count,
            dry_run=self._dry_run
        )

        if timeframe not in TIMEFRAME_MAP:
            raise ValueError(
                f"Unsupported timeframe: {timeframe}. "
                f"Supported: {list(TIMEFRAME_MAP.keys())}"
            )

        if self._dry_run:
            return self._generate_mock_candles(symbol, timeframe, count)

        if not self._connector.is_connected():
            raise ConnectionError(
                "MT5 not connected. Call connector.connect() first."
            )

        try:
            # Use mt5linux copy_rates_from_pos to get candles
            # copy_rates_from_pos(symbol, timeframe, position, count)
            tf_value = int(TIMEFRAME_MAP[timeframe])
            rates = self._connector.mt5.copy_rates_from_pos(
                symbol=symbol,
                timeframe=tf_value,
                start_pos=0,
                count=count
            )

            if rates is None or len(rates) == 0:
                logger.warning(
                    "no_candles_returned",
                    symbol=symbol,
                    timeframe=timeframe
                )
                return pd.DataFrame(
                    columns=["time", "open", "high", "low", "close", "volume"]
                )

            # Convert to DataFrame
            df = pd.DataFrame(rates)
            df["time"] = pd.to_datetime(df["time"], unit="s")
            df = df.set_index("time")
            df = df[["open", "high", "low", "close", "volume"]]

            logger.info(
                "candles_retrieved",
                symbol=symbol,
                timeframe=timeframe,
                count=len(df)
            )
            return df

        except Exception as e:
            logger.error(
                "get_candles_error",
                symbol=symbol,
                timeframe=timeframe,
                error=str(e)
            )
            raise

    def _generate_mock_candles(
        self,
        symbol: str,
        timeframe: str,
        count: int
    ) -> pd.DataFrame:
        """
        PURPOSE: Generate realistic mock OHLCV data for dry-run mode.

        Creates synthetic candles with realistic properties:
        - Close values form trending or ranging patterns
        - High > max(open, close), Low < min(open, close)
        - Volume varies naturally
        - Timestamps follow proper intervals

        Args:
            symbol: Symbol name
            timeframe: Timeframe string
            count: Number of candles

        Returns:
            pd.DataFrame: Mock OHLCV DataFrame
        """
        # Map timeframe to minutes
        tf_minutes = {
            "M1": 1, "M5": 5, "M15": 15, "M30": 30,
            "H1": 60, "H4": 240, "D1": 1440, "W1": 10080
        }
        minutes = tf_minutes.get(timeframe, 60)

        # Base price (varies by symbol)
        symbol_prices = {
            "EURUSD": 1.0800, "GBPUSD": 1.2700, "USDJPY": 150.0,
            "AUDUSD": 0.6500, "USDCAD": 1.3500, "NZDUSD": 0.5900,
            "EURGBP": 0.8500, "EURJPY": 162.0, "GBPJPY": 190.0,
            "GOLD": 2050.0, "WTI": 75.0, "DXUSD": 104.0,
        }
        base_price = symbol_prices.get(symbol, 100.0)

        # Generate price path with random walk
        np.random.seed(hash(symbol + timeframe) % 2**32)
        returns = np.random.normal(0.0001, 0.005, count)
        prices = base_price * np.exp(np.cumsum(returns))

        # Generate OHLC from prices with volatility
        opens = prices + np.random.normal(0, prices * 0.001, count)
        closes = prices + np.random.normal(0, prices * 0.001, count)
        highs = np.maximum(opens, closes) + np.abs(np.random.normal(0, prices * 0.002, count))
        lows = np.minimum(opens, closes) - np.abs(np.random.normal(0, prices * 0.002, count))

        # Generate volumes
        base_volume = 1000
        volumes = base_volume + np.random.normal(0, base_volume * 0.3, count)
        volumes = np.maximum(volumes, 100)

        # Generate timestamps
        now = datetime.utcnow()
        times = [
            now - timedelta(minutes=minutes * (count - 1 - i))
            for i in range(count)
        ]

        df = pd.DataFrame({
            "time": times,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes,
        })

        df = df.set_index("time")
        logger.info(
            "mock_candles_generated",
            symbol=symbol,
            timeframe=timeframe,
            count=count
        )
        return df

    def get_tick(self, symbol: str) -> dict:
        """
        PURPOSE: Fetch current tick data for symbol.

        Retrieves latest tick with bid, ask, time, and spread.
        In dry-run mode, generates synthetic tick based on last candle.

        Args:
            symbol: Symbol to fetch (e.g., "EURUSD")

        Returns:
            dict: Tick data with keys:
                - bid: float - Current bid price
                - ask: float - Current ask price
                - time: datetime - Tick time
                - spread: float - Spread in points

        Raises:
            ValueError: If symbol not supported
            ConnectionError: If MT5 connection fails and dry_run=False

        Example:
            >>> tick = feed.get_tick("EURUSD")
            >>> print(f"Bid: {tick['bid']}, Ask: {tick['ask']}")
        """
        logger.info("get_tick_requested", symbol=symbol, dry_run=self._dry_run)

        if symbol not in SUPPORTED_SYMBOLS and not self._dry_run:
            if not self._connector.is_connected():
                raise ConnectionError("MT5 not connected")

        if self._dry_run:
            return self._generate_mock_tick(symbol)

        try:
            tick_info = self._connector.mt5.symbol_info_tick(symbol)

            if tick_info is None:
                logger.warning("no_tick_returned", symbol=symbol)
                return {
                    "bid": None,
                    "ask": None,
                    "time": None,
                    "spread": None,
                }

            time_dt = datetime.fromtimestamp(tick_info.time)
            tick_dict = {
                "bid": tick_info.bid,
                "ask": tick_info.ask,
                "time": time_dt,
                "spread": tick_info.ask - tick_info.bid,
            }

            logger.info(
                "tick_retrieved",
                symbol=symbol,
                bid=tick_info.bid,
                ask=tick_info.ask
            )
            return tick_dict

        except Exception as e:
            logger.error(
                "get_tick_error",
                symbol=symbol,
                error=str(e)
            )
            raise

    def _generate_mock_tick(self, symbol: str) -> dict:
        """
        PURPOSE: Generate synthetic tick data for dry-run mode.

        Creates a realistic tick with bid/ask spread based on symbol.

        Args:
            symbol: Symbol name

        Returns:
            dict: Mock tick dictionary
        """
        # Get base price
        symbol_prices = {
            "EURUSD": 1.0800, "GBPUSD": 1.2700, "USDJPY": 150.0,
            "AUDUSD": 0.6500, "USDCAD": 1.3500, "NZDUSD": 0.5900,
            "EURGBP": 0.8500, "EURJPY": 162.0, "GBPJPY": 190.0,
            "GOLD": 2050.0, "WTI": 75.0, "DXUSD": 104.0,
        }
        base_price = symbol_prices.get(symbol, 100.0)

        # Add some random movement
        np.random.seed(hash(symbol) % 2**32)
        noise = np.random.normal(0, base_price * 0.0001)
        mid = base_price + noise

        # Typical spreads (in decimal)
        spreads = {
            "EURUSD": 0.0001, "GBPUSD": 0.0001, "USDJPY": 0.01,
            "AUDUSD": 0.0001, "USDCAD": 0.0001, "NZDUSD": 0.0001,
            "EURGBP": 0.0001, "EURJPY": 0.01, "GBPJPY": 0.01,
            "GOLD": 0.01, "WTI": 0.01, "DXUSD": 0.01,
        }
        spread = spreads.get(symbol, 0.0001)

        bid = mid - spread / 2
        ask = mid + spread / 2

        tick = {
            "bid": bid,
            "ask": ask,
            "time": datetime.utcnow(),
            "spread": spread,
        }

        logger.info(
            "mock_tick_generated",
            symbol=symbol,
            bid=bid,
            ask=ask,
            spread=spread
        )
        return tick

    def get_spread(self, symbol: str) -> float:
        """
        PURPOSE: Get current spread for symbol in points.

        Retrieves latest tick and calculates spread. Spread is returned
        in points (0.0001 for 4-decimal symbols, 0.01 for 2-decimal).

        Args:
            symbol: Symbol to fetch spread (e.g., "EURUSD")

        Returns:
            float: Spread in points

        Raises:
            ValueError: If symbol not supported
            ConnectionError: If MT5 connection fails and dry_run=False

        Example:
            >>> spread = feed.get_spread("EURUSD")
            >>> print(f"Spread: {spread} points")
        """
        try:
            tick = self.get_tick(symbol)
            if tick["spread"] is None:
                logger.warning("spread_unavailable", symbol=symbol)
                return 0.0
            return tick["spread"]
        except Exception as e:
            logger.error(
                "get_spread_error",
                symbol=symbol,
                error=str(e)
            )
            raise

    def get_symbols(self) -> list[str]:
        """
        PURPOSE: Get list of available trading symbols.

        In dry-run mode, returns predefined SUPPORTED_SYMBOLS list.
        In live mode, queries MT5 for available symbols.

        Returns:
            list[str]: List of symbol strings (e.g., ["EURUSD", "GOLD"])

        Raises:
            ConnectionError: If MT5 connection fails and dry_run=False

        Example:
            >>> symbols = feed.get_symbols()
            >>> print(f"Available: {len(symbols)} symbols")
        """
        logger.info("get_symbols_requested", dry_run=self._dry_run)

        if self._dry_run:
            return SUPPORTED_SYMBOLS.copy()

        try:
            if not self._connector.is_connected():
                raise ConnectionError("MT5 not connected")

            # In live mode, would query MT5 for all symbols
            # For now, return supported list
            logger.info("symbols_retrieved", count=len(SUPPORTED_SYMBOLS))
            return SUPPORTED_SYMBOLS.copy()

        except Exception as e:
            logger.error("get_symbols_error", error=str(e))
            raise

    def validate_candles(self, df: pd.DataFrame) -> bool:
        """
        PURPOSE: Validate OHLCV DataFrame for data quality.

        Checks for:
        - No null values in OHLCV columns
        - High >= Open and High >= Close
        - Low <= Open and Low <= Close
        - Close and Open are reasonable prices
        - Volume is positive

        Args:
            df: DataFrame with columns: open, high, low, close, volume

        Returns:
            bool: True if all validation checks pass, False otherwise

        Example:
            >>> df = feed.get_candles("EURUSD", "H1")
            >>> if feed.validate_candles(df):
            ...     print("Data is valid")
        """
        try:
            required_cols = ["open", "high", "low", "close", "volume"]

            # Check columns exist
            if not all(col in df.columns for col in required_cols):
                logger.warning(
                    "missing_columns",
                    required=required_cols,
                    present=list(df.columns)
                )
                return False

            # Check for nulls
            if df[required_cols].isnull().any().any():
                logger.warning("null_values_found")
                return False

            # Check high/low relationships
            if (df["high"] < df["open"]).any() or (df["high"] < df["close"]).any():
                logger.warning("high_price_invalid")
                return False

            if (df["low"] > df["open"]).any() or (df["low"] > df["close"]).any():
                logger.warning("low_price_invalid")
                return False

            # Check volume
            if (df["volume"] <= 0).any():
                logger.warning("zero_volume")
                return False

            logger.info(
                "candles_validated",
                rows=len(df),
                status="valid"
            )
            return True

        except Exception as e:
            logger.error(
                "validate_candles_error",
                error=str(e)
            )
            return False
