"""
PURPOSE: Synthetic market data generator for DRY_RUN mode without MT5.

Generates realistic-looking OHLCV candle data using random walks when the
MT5 bridge is unavailable. Used ONLY in DRY_RUN mode as a fallback.

CALLED BY: data_feed.py (when MT5 connection fails and DRY_RUN=True)
"""

import time
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict

from app.utils.logger import get_logger

logger = get_logger("bridge.synthetic_feed")

# Base prices for common forex/commodity symbols
SYMBOL_BASE_PRICES: Dict[str, float] = {
    "EURUSD": 1.0850,
    "GBPUSD": 1.2650,
    "USDJPY": 149.50,
    "XAUUSD": 2030.00,
    "AUDUSD": 0.6550,
    "USDCAD": 1.3550,
    "USDCHF": 0.8750,
    "NZDUSD": 0.6150,
}

# Volatility (ATR as % of price) per symbol
SYMBOL_VOLATILITY: Dict[str, float] = {
    "EURUSD": 0.0005,
    "GBPUSD": 0.0007,
    "USDJPY": 0.08,
    "XAUUSD": 5.0,
    "AUDUSD": 0.0005,
    "USDCAD": 0.0005,
    "USDCHF": 0.0005,
    "NZDUSD": 0.0005,
}

# Timeframe to minutes mapping
TIMEFRAME_MINUTES = {
    "M1": 1, "M5": 5, "M15": 15, "M30": 30,
    "H1": 60, "H4": 240, "D1": 1440, "W1": 10080,
}


class SyntheticFeed:
    """
    PURPOSE: Generate synthetic OHLCV data for testing without MT5.

    Uses geometric Brownian motion with mean-reverting tendencies to
    generate price series that look somewhat realistic.
    """

    def __init__(self):
        self._price_state: Dict[str, float] = {}
        self._seed = int(time.time()) % 10000
        logger.info("synthetic_feed_initialized", seed=self._seed)

    def _get_current_price(self, symbol: str) -> float:
        """Get or initialize the current price for a symbol."""
        if symbol not in self._price_state:
            base = SYMBOL_BASE_PRICES.get(symbol, 1.0)
            # Add small random offset
            np.random.seed(self._seed + hash(symbol) % 10000)
            offset = np.random.normal(0, base * 0.005)
            self._price_state[symbol] = base + offset
        return self._price_state[symbol]

    def generate_candles(
        self,
        symbol: str,
        timeframe: str,
        count: int = 200,
    ) -> pd.DataFrame:
        """
        Generate synthetic OHLCV candles.

        Uses random walk with mean reversion to create realistic-looking
        price data. Updates internal price state so consecutive calls
        produce continuous price series.
        """
        vol = SYMBOL_VOLATILITY.get(symbol, 0.0005)
        tf_minutes = TIMEFRAME_MINUTES.get(timeframe, 60)
        current_price = self._get_current_price(symbol)

        # Scale volatility by timeframe
        vol_scale = np.sqrt(tf_minutes / 60.0)
        step_vol = vol * vol_scale

        # Generate random returns with slight mean reversion
        np.random.seed(int(time.time()) + hash(f"{symbol}_{timeframe}") % 10000)
        returns = np.random.normal(0, step_vol, count)

        # Build price series
        prices = np.zeros(count)
        prices[0] = current_price
        base_price = SYMBOL_BASE_PRICES.get(symbol, current_price)

        for i in range(1, count):
            # Mean reversion force
            mean_rev = -0.01 * (prices[i - 1] - base_price) / base_price
            prices[i] = prices[i - 1] * (1 + returns[i] + mean_rev)

        # Generate OHLC from close prices
        now = datetime.utcnow()
        times = [now - timedelta(minutes=tf_minutes * (count - i)) for i in range(count)]

        data = []
        for i in range(count):
            close = prices[i]
            # Generate intra-candle variation
            intra_vol = step_vol * 0.5
            o = close * (1 + np.random.normal(0, intra_vol))
            h = max(o, close) * (1 + abs(np.random.normal(0, intra_vol)))
            l = min(o, close) * (1 - abs(np.random.normal(0, intra_vol)))
            volume = int(np.random.exponential(1000))

            data.append({
                "time": times[i],
                "open": round(o, 5),
                "high": round(h, 5),
                "low": round(l, 5),
                "close": round(close, 5),
                "tick_volume": volume,
                "spread": 2,
                "real_volume": 0,
            })

        # Update price state to last close
        self._price_state[symbol] = prices[-1]

        df = pd.DataFrame(data)
        df = df.set_index("time")
        df["volume"] = df["tick_volume"]

        logger.debug(
            "synthetic_candles_generated",
            symbol=symbol,
            timeframe=timeframe,
            count=count,
            last_close=round(prices[-1], 5),
        )

        return df

    def generate_tick(self, symbol: str) -> dict:
        """Generate a synthetic tick."""
        price = self._get_current_price(symbol)
        vol = SYMBOL_VOLATILITY.get(symbol, 0.0005)
        spread = vol * 0.5

        return {
            "bid": round(price, 5),
            "ask": round(price + spread, 5),
            "last": round(price, 5),
            "time": datetime.utcnow(),
            "spread": round(spread * 100000, 1) if price < 10 else round(spread * 100, 1),
            "spread_raw": round(spread, 5),
        }

    def get_symbols(self) -> list[str]:
        """Return list of synthetic symbols."""
        return list(SYMBOL_BASE_PRICES.keys())
