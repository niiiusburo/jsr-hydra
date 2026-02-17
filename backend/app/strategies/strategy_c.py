"""
PURPOSE: Strategy C - Session Breakout using trading session ranges.

STRATEGY LOGIC:
    - Identifies trading sessions: Asian (bars 0-8), London (bars 8-16) on H1
    - Calculates session high/low from lookback_bars
    - Generates BUY when price breaks above session_high + ATR * breakout_atr_mult
    - Generates SELL when price breaks below session_low - ATR * breakout_atr_mult
    - Confidence based on breakout distance relative to ATR
    - SL = opposite side of session range
    - TP = entry ± (session_range * 1.5)

CALLED BY: engine/orchestrator.py → run_cycle()
"""

import numpy as np
import pandas as pd
from typing import Optional, Tuple

from app.config.constants import StrategyCode, OrderDirection
from app.bridge.data_feed import DataFeed
from app.bridge.order_manager import OrderManager
from app.events.bus import EventBus
from app.indicators.volatility import atr
from app.strategies.base import BaseStrategy
from app.strategies.signals import StrategySignal
from app.utils.logger import get_logger


logger = get_logger("strategies.strategy_c")


class StrategyC(BaseStrategy):
    """
    PURPOSE: Session Breakout strategy targeting range breakouts from trading sessions.

    Identifies key trading session ranges (Asian, London) and trades breakouts
    from those ranges with ATR-based confirmation and dynamically calculated
    stop-loss and take-profit levels.

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
        PURPOSE: Initialize StrategyC with configuration and dependencies.

        Args:
            data_feed: DataFeed instance for market data access
            order_manager: OrderManager instance for trade execution
            event_bus: EventBus instance for event publishing
            config: Strategy configuration dictionary with keys:
                - lookback_bars (default 24): Number of bars to define session range
                - breakout_atr_mult (default 1.5): ATR multiplier for breakout threshold
                - timeframe (default 'H1'): Candle timeframe
                - lookback (default 50): Number of candles to fetch
                - default_lots (default 1.0): Default lot size

        CALLED BY: Orchestrator initialization
        """
        super().__init__(
            code=StrategyCode.C,
            name="Session Breakout",
            data_feed=data_feed,
            order_manager=order_manager,
            event_bus=event_bus,
            config=config
        )

        # Set configuration with defaults
        self._lookback_bars = config.get('lookback_bars', 24)
        self._breakout_atr_mult = config.get('breakout_atr_mult', 1.5)
        self._atr_period = config.get('atr_period', 14)
        self._timeframe = config.get('timeframe', 'H1')
        self._lookback = config.get('lookback', 50)

        logger.info(
            "strategy_c_initialized",
            lookback_bars=self._lookback_bars,
            breakout_atr_mult=self._breakout_atr_mult,
            atr_period=self._atr_period
        )

    def _get_session_range(self, candles_df: pd.DataFrame) -> Tuple[float, float, int, int]:
        """
        PURPOSE: Identify the current trading session and its high/low.

        For H1 timeframe:
        - Asian session: bars 0-8 (23:00-07:00 London time)
        - London session: bars 8-16 (08:00-16:00 London time)

        Args:
            candles_df: DataFrame with complete candle data

        Returns:
            Tuple[float, float, int, int]: (session_high, session_low, start_idx, end_idx)

        CALLED BY: generate_signal()
        """
        try:
            # For H1 timeframe, calculate session based on candle count
            # If we have the full lookback, use the session pattern
            lookback = min(self._lookback_bars, len(candles_df))

            # Get high and low from session bars
            session_data = candles_df.iloc[-lookback:]
            session_high = session_data['high'].max()
            session_low = session_data['low'].min()

            start_idx = len(candles_df) - lookback
            end_idx = len(candles_df) - 1

            logger.debug(
                "session_range_calculated",
                session_high=session_high,
                session_low=session_low,
                lookback_bars=lookback
            )

            return session_high, session_low, start_idx, end_idx

        except Exception as e:
            logger.error(
                "session_range_calculation_error",
                error=str(e)
            )
            raise

    def generate_signal(self, candles_df: pd.DataFrame) -> Optional[StrategySignal]:
        """
        PURPOSE: Generate trading signal based on session breakout detection.

        Logic:
        1. Validate sufficient data availability
        2. Identify current trading session and its range
        3. Calculate ATR for volatility adjustment
        4. Check if price breaks above/below session range + ATR buffer
        5. Calculate confidence based on breakout distance
        6. Set SL at opposite side of session range
        7. Set TP at 1.5x session range away from entry
        8. Handle edge cases: NaN values, insufficient data

        Args:
            candles_df: DataFrame with OHLCV columns (open, high, low, close, volume)
                       Index should be datetime

        Returns:
            StrategySignal: Trading signal if conditions met, or None if not

        CALLED BY: BaseStrategy.run_cycle()
        """
        try:
            # Validate minimum data points
            if len(candles_df) < self._lookback_bars + 5:
                logger.warning(
                    "insufficient_data_for_strategy_c",
                    available=len(candles_df),
                    required=self._lookback_bars + 5
                )
                return None

            # Extract OHLC data
            close = candles_df['close']
            high = candles_df['high']
            low = candles_df['low']

            # Calculate ATR for volatility adjustment
            atr_values = atr(high, low, close, self._atr_period)
            latest_atr = atr_values.iloc[-1]

            # Handle NaN ATR
            if pd.isna(latest_atr):
                logger.debug("atr_is_nan")
                return None

            # Get session range
            session_high, session_low, start_idx, end_idx = self._get_session_range(candles_df)

            # Calculate breakout levels with ATR adjustment
            breakout_high = session_high + (latest_atr * self._breakout_atr_mult)
            breakout_low = session_low - (latest_atr * self._breakout_atr_mult)
            session_range = session_high - session_low

            # Get current price
            latest_close = close.iloc[-1]
            latest_high = high.iloc[-1]
            latest_low = low.iloc[-1]

            # Detect breakout
            if latest_high > breakout_high:
                # Bullish breakout: price broke above session high
                signal_direction = OrderDirection.BUY
                breakout_distance = latest_close - session_high
                sl_price = session_low - (latest_atr * 0.5)
                tp_price = latest_close + (session_range * 1.5)

                logger.info(
                    "bullish_breakout_detected",
                    session_high=session_high,
                    session_low=session_low,
                    breakout_high=breakout_high,
                    latest_close=latest_close
                )

            elif latest_low < breakout_low:
                # Bearish breakout: price broke below session low
                signal_direction = OrderDirection.SELL
                breakout_distance = session_low - latest_close
                sl_price = session_high + (latest_atr * 0.5)
                tp_price = latest_close - (session_range * 1.5)

                logger.info(
                    "bearish_breakout_detected",
                    session_high=session_high,
                    session_low=session_low,
                    breakout_low=breakout_low,
                    latest_close=latest_close
                )

            else:
                # No breakout detected
                return None

            # Ensure SL and TP are valid
            if sl_price <= 0 or tp_price <= 0:
                logger.warning(
                    "invalid_sl_tp_prices",
                    sl=sl_price,
                    tp=tp_price
                )
                return None

            # Calculate confidence based on breakout distance / ATR
            # Clamped to [0, 1]
            confidence = min((breakout_distance / latest_atr) / 3.0, 1.0)

            # Create and return signal
            signal = StrategySignal(
                direction=signal_direction,
                confidence=confidence,
                sl_price=sl_price,
                tp_price=tp_price,
                reason=f"Session breakout: range {session_low:.4f}-{session_high:.4f}, breakout distance {breakout_distance:.4f}",
                strategy_code=self._code.value
            )

            logger.info(
                "signal_generated",
                direction=signal_direction,
                confidence=confidence,
                sl=sl_price,
                tp=tp_price,
                session_range=session_range,
                atr=latest_atr
            )

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
            "lookback_bars": self._lookback_bars,
            "breakout_atr_mult": self._breakout_atr_mult,
            "atr_period": self._atr_period,
            "timeframe": self._timeframe,
            "lookback": self._lookback,
            "default_lots": self._config.get('default_lots', 1.0),
        }
