"""
MT5 Data Feed Module

PURPOSE: Provide OHLCV candle data and tick data from MT5 via HTTP REST bridge.
Always uses real MT5 data (even in DRY_RUN mode -- DRY_RUN only suppresses orders).

CALLED BY:
    - strategies
    - analysis engines
    - backtesting systems
"""

from datetime import datetime
from typing import Optional
import pandas as pd

from app.bridge.connector import MT5Connector
from app.utils.logger import get_logger

logger = get_logger("bridge.data_feed")

# Supported timeframes (MT5 format string -> REST API path value)
TIMEFRAME_MAP = {
    "M1": "M1",
    "M5": "M5",
    "M15": "M15",
    "M30": "M30",
    "H1": "H1",
    "H4": "H4",
    "D1": "D1",
    "W1": "W1",
}


class DataFeed:
    """
    PURPOSE: Fetch OHLCV candles and tick data from MT5 REST bridge.

    All data comes from the real MT5 terminal via HTTP. When MT5 is unavailable
    and a synthetic_feed is attached, falls back to synthetic data.
    DRY_RUN mode still uses live market data when available.

    Attributes:
        _connector: MT5Connector instance (HTTP-based)
        _synthetic_feed: Optional SyntheticFeed for fallback when MT5 unavailable
    """

    def __init__(self, connector: MT5Connector, dry_run: bool = True):
        """
        PURPOSE: Initialize DataFeed with connector.

        Args:
            connector: MT5Connector instance for REST API calls.
            dry_run: Accepted for interface compatibility but ignored for data.
                     Data feed ALWAYS uses real MT5 data.
        """
        self._connector = connector
        self._synthetic_feed = None  # Set by engine when MT5 is unavailable
        # NOTE: dry_run is intentionally ignored for data retrieval.
        # Real prices are always fetched from MT5.
        logger.info("data_feed_initialized", dry_run=dry_run, note="always_real_data")

    def set_synthetic_fallback(self, synthetic_feed) -> None:
        """Attach a SyntheticFeed for use when MT5 is unavailable."""
        self._synthetic_feed = synthetic_feed
        logger.info("synthetic_fallback_attached")

    async def get_candles(
        self,
        symbol: str,
        timeframe: str,
        count: int = 200,
    ) -> pd.DataFrame:
        """
        PURPOSE: Fetch OHLCV candles for symbol and timeframe from MT5 REST bridge.

        Calls GET /candles/{symbol}/{timeframe}/{count} and returns a validated
        pandas DataFrame. No mock data is ever generated.

        Args:
            symbol: Symbol to fetch (e.g., "EURUSD", "GOLD")
            timeframe: Timeframe as string (e.g., "H1", "D1", "M15")
            count: Number of candles to fetch. Default: 200

        Returns:
            pd.DataFrame: DataFrame with columns:
                - time: datetime - Candle open time (index)
                - open: float
                - high: float
                - low: float
                - close: float
                - tick_volume: float
                - spread: int
                - real_volume: float

        Raises:
            ValueError: If timeframe not supported
            ConnectionError: If MT5 REST call fails
        """
        logger.info(
            "get_candles_requested",
            symbol=symbol,
            timeframe=timeframe,
            count=count,
        )

        if timeframe not in TIMEFRAME_MAP:
            raise ValueError(
                f"Unsupported timeframe: {timeframe}. "
                f"Supported: {list(TIMEFRAME_MAP.keys())}"
            )

        tf = TIMEFRAME_MAP[timeframe]

        try:
            client = await self._connector._get_client()
            resp = await client.get(f"/candles/{symbol}/{tf}/{count}")
            resp.raise_for_status()
            candles = resp.json()

            if not candles:
                logger.warning(
                    "no_candles_returned",
                    symbol=symbol,
                    timeframe=timeframe,
                )
                return pd.DataFrame(
                    columns=["time", "open", "high", "low", "close", "tick_volume", "spread", "real_volume"]
                )

            df = pd.DataFrame(candles)

            # Normalise time column to datetime
            if "time" in df.columns:
                # Server may return epoch seconds or ISO string
                sample = df["time"].iloc[0]
                if isinstance(sample, (int, float)):
                    df["time"] = pd.to_datetime(df["time"], unit="s")
                else:
                    df["time"] = pd.to_datetime(df["time"])

            df = df.set_index("time")

            # Provide a 'volume' alias pointing to tick_volume for backward compat
            if "tick_volume" in df.columns and "volume" not in df.columns:
                df["volume"] = df["tick_volume"]

            # Validate
            if not self.validate_candles(df):
                logger.warning("candle_validation_failed", symbol=symbol, timeframe=timeframe)

            logger.info(
                "candles_retrieved",
                symbol=symbol,
                timeframe=timeframe,
                count=len(df),
            )
            return df

        except Exception as e:
            # Fall back to synthetic data if available
            if self._synthetic_feed is not None:
                logger.info(
                    "using_synthetic_candles",
                    symbol=symbol,
                    timeframe=timeframe,
                    reason=str(e),
                )
                return self._synthetic_feed.generate_candles(symbol, timeframe, count)
            logger.error(
                "get_candles_error",
                symbol=symbol,
                timeframe=timeframe,
                error=str(e),
            )
            raise ConnectionError(f"Failed to get candles for {symbol}/{timeframe}: {e}")

    async def get_tick(self, symbol: str) -> dict:
        """
        PURPOSE: Fetch current tick data for symbol from MT5 REST bridge.

        Calls GET /tick/{symbol}.

        Args:
            symbol: Symbol to fetch (e.g., "EURUSD")

        Returns:
            dict: Tick data with keys: bid, ask, last, time, spread, spread_raw

        Raises:
            ConnectionError: If MT5 REST call fails
        """
        logger.info("get_tick_requested", symbol=symbol)

        try:
            client = await self._connector._get_client()
            resp = await client.get(f"/tick/{symbol}")
            resp.raise_for_status()
            tick = resp.json()

            # Normalise time field
            if tick.get("time") and isinstance(tick["time"], (int, float)):
                tick["time"] = datetime.fromtimestamp(tick["time"])

            logger.info(
                "tick_retrieved",
                symbol=symbol,
                bid=tick.get("bid"),
                ask=tick.get("ask"),
            )
            return tick

        except Exception as e:
            if self._synthetic_feed is not None:
                return self._synthetic_feed.generate_tick(symbol)
            logger.error("get_tick_error", symbol=symbol, error=str(e))
            raise ConnectionError(f"Failed to get tick for {symbol}: {e}")

    async def get_spread(self, symbol: str) -> float:
        """
        PURPOSE: Get current spread for symbol.

        Args:
            symbol: Symbol to fetch spread (e.g., "EURUSD")

        Returns:
            float: Spread value from the tick endpoint.
        """
        try:
            tick = await self.get_tick(symbol)
            spread = tick.get("spread")
            if spread is None:
                # Fall back to bid/ask difference
                bid = tick.get("bid")
                ask = tick.get("ask")
                if bid is not None and ask is not None:
                    return float(ask - bid)
                logger.warning("spread_unavailable", symbol=symbol)
                return 0.0
            return float(spread)
        except Exception as e:
            logger.error("get_spread_error", symbol=symbol, error=str(e))
            raise

    async def get_symbols(self) -> list[str]:
        """
        PURPOSE: Get list of available trading symbol names from MT5.

        Calls GET /symbols on the REST bridge and extracts symbol names.

        Returns:
            list[str]: List of symbol name strings.
        """
        logger.info("get_symbols_requested")

        try:
            symbols_data = await self._connector.get_symbols()
            # Handle both formats: list of strings or list of dicts
            names = [
                s["name"] if isinstance(s, dict) else s
                for s in symbols_data
                if (isinstance(s, dict) and "name" in s) or isinstance(s, str)
            ]
            logger.info("symbols_retrieved", count=len(names))
            return names
        except Exception as e:
            logger.error("get_symbols_error", error=str(e))
            raise

    def validate_candles(self, df: pd.DataFrame) -> bool:
        """
        PURPOSE: Validate OHLCV DataFrame for data quality.

        Checks for:
        - No null values in OHLC columns
        - High >= max(Open, Close) for each row
        - Low <= min(Open, Close) for each row

        Args:
            df: DataFrame with at least columns: open, high, low, close

        Returns:
            bool: True if all validation checks pass, False otherwise.
        """
        try:
            ohlc_cols = ["open", "high", "low", "close"]

            # Check columns exist
            missing = [c for c in ohlc_cols if c not in df.columns]
            if missing:
                logger.warning("missing_columns", missing=missing, present=list(df.columns))
                return False

            # Check for nulls in OHLC
            if df[ohlc_cols].isnull().any().any():
                logger.warning("null_values_found")
                return False

            # OHLC consistency
            if (df["high"] < df["open"]).any() or (df["high"] < df["close"]).any():
                logger.warning("high_price_invalid")
                return False

            if (df["low"] > df["open"]).any() or (df["low"] > df["close"]).any():
                logger.warning("low_price_invalid")
                return False

            logger.info("candles_validated", rows=len(df), status="valid")
            return True

        except Exception as e:
            logger.error("validate_candles_error", error=str(e))
            return False
