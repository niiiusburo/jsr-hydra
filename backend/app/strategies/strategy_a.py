"""
PURPOSE: Strategy A - Trend Following using EMA crossovers with ADX confirmation.

STRATEGY LOGIC:
    - Identifies trending markets using ADX > threshold
    - Generates BUY when EMA fast crosses above EMA slow AND ADX > threshold
    - Generates SELL when EMA fast crosses below EMA slow AND ADX > threshold
    - In ranging markets (ADX < threshold), no signals generated
    - Uses ATR for dynamic stop-loss and take-profit calculation
    - Confidence = ADX / 50.0, clamped to [0, 1]

CALLED BY: engine/orchestrator.py → run_cycle()
"""

import numpy as np
import pandas as pd
from typing import Optional

from app.config.constants import StrategyCode, OrderDirection
from app.bridge.data_feed import DataFeed
from app.bridge.order_manager import OrderManager
from app.events.bus import EventBus
from app.indicators.trend import ema, adx
from app.indicators.volatility import atr
from app.strategies.base import BaseStrategy
from app.strategies.signals import StrategySignal
from app.utils.logger import get_logger


logger = get_logger("strategies.strategy_a")


class StrategyA(BaseStrategy):
    """
    PURPOSE: Trend Following strategy using EMA crossovers with ADX confirmation.

    Inherits from BaseStrategy and implements trend-following logic based on:
    - Exponential Moving Averages (fast and slow)
    - Average Directional Index (ADX) for trend strength confirmation
    - Average True Range (ATR) for dynamic stop-loss and take-profit levels

    CALLED BY: engine/orchestrator.py
    """

    def __init__(
        self,
        data_feed: DataFeed,
        order_manager: OrderManager,
        event_bus: EventBus,
        config: dict
    ):
        """
        PURPOSE: Initialize StrategyA with configuration and dependencies.

        Args:
            data_feed: DataFeed instance for market data access
            order_manager: OrderManager instance for trade execution
            event_bus: EventBus instance for event publishing
            config: Strategy configuration dictionary with keys:
                - ema_fast (default 9): Fast EMA period
                - ema_slow (default 21): Slow EMA period
                - atr_period (default 14): ATR period for volatility
                - adx_threshold (default 25): Minimum ADX for trend confirmation
                - timeframe (default 'H1'): Candle timeframe
                - lookback (default 50): Number of candles to fetch
                - default_lots (default 1.0): Default lot size

        CALLED BY: Orchestrator initialization
        """
        super().__init__(
            code=StrategyCode.A,
            name="Trend Following (EMA + ADX)",
            data_feed=data_feed,
            order_manager=order_manager,
            event_bus=event_bus,
            config=config
        )

        # Set configuration with defaults
        self._ema_fast = config.get('ema_fast', 9)
        self._ema_slow = config.get('ema_slow', 21)
        self._atr_period = config.get('atr_period', 14)
        self._adx_threshold = config.get('adx_threshold', 25)
        self._timeframe = config.get('timeframe', 'H1')
        self._lookback = config.get('lookback', 50)

        # Track last signal to avoid duplicate signals
        self._last_signal_direction: Optional[str] = None
        self._last_ema_fast_above_slow: Optional[bool] = None

        logger.info(
            "strategy_a_initialized",
            ema_fast=self._ema_fast,
            ema_slow=self._ema_slow,
            atr_period=self._atr_period,
            adx_threshold=self._adx_threshold
        )

    def generate_signal(self, candles_df: pd.DataFrame) -> Optional[StrategySignal]:
        """
        PURPOSE: Generate trading signal based on EMA crossover with ADX confirmation.

        Logic:
        1. Validate sufficient data availability
        2. Calculate EMA fast, EMA slow, ADX, and ATR
        3. Check if ADX > threshold (trending market confirmation)
        4. Detect EMA crossover (fast crossing above/below slow)
        5. Generate BUY/SELL signal with ATR-based SL and TP
        6. Calculate confidence based on ADX strength
        7. Handle edge cases: NaN values, insufficient data, ranging markets

        Args:
            candles_df: DataFrame with OHLCV columns (open, high, low, close, volume)
                       Index should be datetime

        Returns:
            StrategySignal: Trading signal if conditions met, or None if not

        CALLED BY: BaseStrategy.run_cycle()
        """
        try:
            # Validate minimum data points
            if len(candles_df) < self._ema_slow + 5:
                logger.warning(
                    "insufficient_data_for_strategy_a",
                    available=len(candles_df),
                    required=self._ema_slow + 5
                )
                return None

            # Extract OHLC data
            close = candles_df['close']
            high = candles_df['high']
            low = candles_df['low']

            # Calculate indicators
            ema_fast = ema(close, self._ema_fast)
            ema_slow = ema(close, self._ema_slow)
            adx_values = adx(high, low, close, self._atr_period)
            atr_values = atr(high, low, close, self._atr_period)

            # Get latest values
            latest_ema_fast = ema_fast.iloc[-1]
            latest_ema_slow = ema_slow.iloc[-1]
            latest_adx = adx_values.iloc[-1]
            latest_atr = atr_values.iloc[-1]
            latest_close = close.iloc[-1]

            # Handle NaN values
            if pd.isna(latest_ema_fast) or pd.isna(latest_ema_slow) or pd.isna(latest_adx) or pd.isna(latest_atr):
                logger.debug(
                    "nan_values_in_indicators",
                    ema_fast_nan=pd.isna(latest_ema_fast),
                    ema_slow_nan=pd.isna(latest_ema_slow),
                    adx_nan=pd.isna(latest_adx),
                    atr_nan=pd.isna(latest_atr)
                )
                return None

            # Check if market is trending (ADX > threshold)
            if latest_adx < self._adx_threshold:
                logger.debug(
                    "market_not_trending",
                    adx=latest_adx,
                    threshold=self._adx_threshold
                )
                # No signal in ranging markets
                self._last_signal_direction = None
                return None

            # Check for EMA crossover
            current_ema_fast_above_slow = latest_ema_fast > latest_ema_slow

            # Get previous EMA values for crossover detection
            prev_ema_fast = ema_fast.iloc[-2] if len(ema_fast) > 1 else None
            prev_ema_slow = ema_slow.iloc[-2] if len(ema_slow) > 1 else None

            if prev_ema_fast is None or prev_ema_slow is None:
                logger.debug("insufficient_history_for_crossover_detection")
                return None

            prev_ema_fast_above_slow = prev_ema_fast > prev_ema_slow

            # Detect crossover
            if current_ema_fast_above_slow and not prev_ema_fast_above_slow:
                # Bullish crossover: EMA fast crossed above EMA slow
                signal_direction = OrderDirection.BUY
                logger.info(
                    "bullish_ema_crossover_detected",
                    ema_fast=latest_ema_fast,
                    ema_slow=latest_ema_slow,
                    adx=latest_adx
                )
            elif not current_ema_fast_above_slow and prev_ema_fast_above_slow:
                # Bearish crossover: EMA fast crossed below EMA slow
                signal_direction = OrderDirection.SELL
                logger.info(
                    "bearish_ema_crossover_detected",
                    ema_fast=latest_ema_fast,
                    ema_slow=latest_ema_slow,
                    adx=latest_adx
                )
            else:
                # No crossover detected
                return None

            # Calculate stop-loss and take-profit using ATR
            if signal_direction == OrderDirection.BUY:
                sl_price = latest_close - (atr_values.iloc[-1] * 2.0)
                tp_price = latest_close + (atr_values.iloc[-1] * 3.0)
            else:  # SELL
                sl_price = latest_close + (atr_values.iloc[-1] * 2.0)
                tp_price = latest_close - (atr_values.iloc[-1] * 3.0)

            # Ensure SL and TP are valid
            if sl_price <= 0 or tp_price <= 0:
                logger.warning(
                    "invalid_sl_tp_prices",
                    sl=sl_price,
                    tp=tp_price
                )
                return None

            # Calculate confidence based on ADX (0-1 scale, clamped)
            confidence = min(latest_adx / 50.0, 1.0)

            # Create and return signal
            signal = StrategySignal(
                direction=signal_direction,
                confidence=confidence,
                sl_price=sl_price,
                tp_price=tp_price,
                reason=f"EMA {self._ema_fast}/{self._ema_slow} crossover with ADX={latest_adx:.2f}",
                strategy_code=self._code.value
            )

            logger.info(
                "signal_generated",
                direction=signal_direction,
                confidence=confidence,
                sl=sl_price,
                tp=tp_price,
                atr=latest_atr
            )

            self._last_signal_direction = signal_direction

            return signal

        except Exception as e:
            logger.error(
                "generate_signal_error",
                error=str(e),
                error_type=type(e).__name__
            )
            return None

    def get_config(self) -> dict:
        """
        PURPOSE: Return the strategy's current configuration.

        Returns:
            dict: Configuration dictionary with all strategy parameters

        CALLED BY: API endpoints, configuration serialization
        """
        return {
            "ema_fast": self._ema_fast,
            "ema_slow": self._ema_slow,
            "atr_period": self._atr_period,
            "adx_threshold": self._adx_threshold,
            "timeframe": self._timeframe,
            "lookback": self._lookback,
            "default_lots": self._config.get('default_lots', 1.0),
        }
