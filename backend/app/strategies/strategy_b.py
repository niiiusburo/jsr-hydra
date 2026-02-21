"""
PURPOSE: Strategy B - Mean Reversion Grid implementation for JSR Hydra.

Implements a mean reversion strategy using Bollinger Bands and Z-score
analysis. When price deviates significantly from moving average (lower or
upper band), the strategy places grid orders with the expectation that
price will revert to the mean.

CALLED BY: engine/orchestrator.py
"""

from typing import Optional
import numpy as np
import pandas as pd

from app.config.constants import StrategyCode
from app.bridge.data_feed import DataFeed
from app.bridge.order_manager import OrderManager
from app.events.bus import EventBus
from app.indicators.trend import adx as calc_adx
from app.strategies.base import BaseStrategy
from app.strategies.signals import StrategySignal
from app.utils.logger import get_logger


logger = get_logger("strategies.strategy_b")


class StrategyB(BaseStrategy):
    """
    PURPOSE: Mean Reversion Grid strategy using Bollinger Bands and Z-score.

    This strategy detects when price deviates significantly from its moving
    average (beyond Bollinger Bands) and places grid orders expecting mean
    reversion. Includes ATR-based stop-loss and mean price as take-profit.

    CALLED BY: engine/orchestrator.py

    Configuration parameters (from config dict):
        grid_levels: Number of grid orders to place (default: 5)
        grid_spacing_pct: Spacing between grid orders as % (default: 0.5%)
        lookback: Number of periods for SMA/ATR (default: 50)
        z_score_threshold: Z-score threshold for band deviation (default: 2.0)
        timeframe: Candle timeframe (default: 'H1')
        default_lots: Default lot size per trade (default: 1.0)
    """

    def __init__(
        self,
        data_feed: DataFeed,
        order_manager: OrderManager,
        event_bus: EventBus,
        config: dict
    ):
        """
        PURPOSE: Initialize Strategy B with configuration and dependencies.

        Args:
            data_feed: DataFeed instance for market data
            order_manager: OrderManager instance for order execution
            event_bus: EventBus instance for event publishing
            config: Configuration dictionary with grid, lookback, z_score parameters

        CALLED BY: engine/orchestrator.py strategy initialization
        """
        super().__init__(
            code=StrategyCode.B,
            name="Mean Reversion Grid",
            data_feed=data_feed,
            order_manager=order_manager,
            event_bus=event_bus,
            config=config
        )

        # Strategy-specific configuration with defaults
        self._grid_levels = config.get('grid_levels', 5)
        self._grid_spacing_pct = config.get('grid_spacing_pct', 0.5)
        self._lookback = config.get('lookback', 50)
        self._bb_period = config.get('bb_period', 20)
        self._z_score_threshold = config.get('z_score_threshold', 1.5)
        self._adx_max_threshold = config.get('adx_max_threshold', 30)
        self._timeframe = config.get('timeframe', 'H1')
        self._default_lots = config.get('default_lots', 1.0)

        logger.info(
            "strategy_b_initialized",
            grid_levels=self._grid_levels,
            grid_spacing_pct=self._grid_spacing_pct,
            lookback=self._lookback,
            bb_period=self._bb_period,
            z_score_threshold=self._z_score_threshold,
            adx_max_threshold=self._adx_max_threshold
        )

    def generate_signal(self, candles_df: pd.DataFrame) -> Optional[StrategySignal]:
        """
        PURPOSE: Generate a mean reversion signal using Bollinger Bands and Z-score.

        Logic:
        1. Calculate 20-period SMA (moving average / mean)
        2. Calculate standard deviation and Bollinger Bands (SMA ± 2*std)
        3. Calculate Z-score of current price vs SMA
        4. If Z-score < -threshold: BUY signal (price below lower band)
        5. If Z-score > +threshold: SELL signal (price above upper band)
        6. Confidence = min(abs(z_score) / 3.0, 1.0) capped at 1.0
        7. SL = entry price ± ATR * 1.5
        8. TP = SMA (mean reversion target)

        Args:
            candles_df: DataFrame with OHLCV data, indexed by datetime

        Returns:
            StrategySignal: Signal if conditions met, or None if no setup

        CALLED BY: base.py → run_cycle()
        """
        try:
            if len(candles_df) < self._lookback:
                logger.warning(
                    "insufficient_candles",
                    strategy_code=self._code.value,
                    required=self._lookback,
                    available=len(candles_df)
                )
                return None

            # ADX trend filter: block mean-reversion signals in trending markets
            if len(candles_df) >= 20:
                adx_values = calc_adx(
                    candles_df['high'], candles_df['low'], candles_df['close'], period=14
                )
                if not adx_values.empty:
                    latest_adx = adx_values.iloc[-1]
                    if not pd.isna(latest_adx) and latest_adx > self._adx_max_threshold:
                        logger.info(
                            "mean_reversion_blocked_by_adx",
                            strategy_code=self._code.value,
                            adx=latest_adx,
                            threshold=self._adx_max_threshold,
                        )
                        return None

            # Calculate SMA (mean)
            sma = candles_df['close'].rolling(window=self._bb_period, min_periods=1).mean()

            # Calculate standard deviation for Bollinger Bands
            std = candles_df['close'].rolling(window=self._bb_period, min_periods=1).std()

            # Calculate Bollinger Bands
            upper_band = sma + 2 * std
            lower_band = sma - 2 * std

            # Get current price and mean
            current_price = candles_df['close'].iloc[-1]
            current_sma = sma.iloc[-1]
            current_std = std.iloc[-1]

            # Handle edge cases
            if pd.isna(current_sma) or pd.isna(current_std) or current_std == 0:
                logger.warning(
                    "invalid_bollinger_calculation",
                    strategy_code=self._code.value,
                    sma_nan=pd.isna(current_sma),
                    std_nan=pd.isna(current_std)
                )
                return None

            # Calculate Z-score
            z_score = (current_price - current_sma) / current_std

            logger.debug(
                "bollinger_analysis",
                strategy_code=self._code.value,
                current_price=current_price,
                sma=current_sma,
                upper_band=upper_band.iloc[-1],
                lower_band=lower_band.iloc[-1],
                z_score=z_score
            )

            # Calculate ATR for stop-loss placement
            atr = self._calculate_atr(candles_df, period=14)

            if atr is None or atr == 0:
                logger.warning(
                    "atr_calculation_failed",
                    strategy_code=self._code.value
                )
                return None

            # Generate signal based on Z-score threshold
            if z_score < -self._z_score_threshold:
                # BUY signal: price below lower band
                direction = "BUY"
                sl_price = current_price - (atr * 1.5)
                tp_price = current_sma  # Revert to mean
                confidence = min(abs(z_score) / 3.0, 1.0)
                reason = f"Mean reversion: price {current_price:.5f} below lower band {lower_band.iloc[-1]:.5f}. Z-score: {z_score:.2f}"

            elif z_score > self._z_score_threshold:
                # SELL signal: price above upper band
                direction = "SELL"
                sl_price = current_price + (atr * 1.5)
                tp_price = current_sma  # Revert to mean
                confidence = min(abs(z_score) / 3.0, 1.0)
                reason = f"Mean reversion: price {current_price:.5f} above upper band {upper_band.iloc[-1]:.5f}. Z-score: {z_score:.2f}"

            else:
                # No signal when within bands
                logger.debug(
                    "no_mean_reversion_setup",
                    strategy_code=self._code.value,
                    z_score=z_score,
                    threshold=self._z_score_threshold
                )
                return None

            # Validate SL and TP levels
            if direction == "BUY":
                if sl_price >= current_price or tp_price <= current_price:
                    logger.warning(
                        "invalid_buy_levels",
                        strategy_code=self._code.value,
                        entry=current_price,
                        sl=sl_price,
                        tp=tp_price
                    )
                    return None
            else:  # SELL
                if sl_price <= current_price or tp_price >= current_price:
                    logger.warning(
                        "invalid_sell_levels",
                        strategy_code=self._code.value,
                        entry=current_price,
                        sl=sl_price,
                        tp=tp_price
                    )
                    return None

            signal = StrategySignal(
                direction=direction,
                confidence=confidence,
                sl_price=sl_price,
                tp_price=tp_price,
                reason=reason,
                strategy_code=self._code.value
            )

            logger.info(
                "mean_reversion_signal_generated",
                strategy_code=self._code.value,
                direction=direction,
                confidence=confidence,
                z_score=z_score
            )

            return signal

        except Exception as e:
            logger.error(
                "generate_signal_error",
                strategy_code=self._code.value,
                error=str(e)
            )
            return None

    def _calculate_atr(self, candles_df: pd.DataFrame, period: int = 14) -> Optional[float]:
        """
        PURPOSE: Calculate Average True Range for volatility-based stop-loss.

        Calculates ATR using the standard formula:
        True Range = max(high - low, abs(high - prev_close), abs(low - prev_close))
        ATR = SMA of True Range

        Args:
            candles_df: DataFrame with OHLCV data
            period: Lookback period for ATR (default: 14)

        Returns:
            float: Current ATR value, or None if calculation fails

        CALLED BY: generate_signal()
        """
        try:
            if len(candles_df) < period + 1:
                logger.warning(
                    "insufficient_candles_for_atr",
                    required=period + 1,
                    available=len(candles_df)
                )
                return None

            high = candles_df['high'].values
            low = candles_df['low'].values
            close = candles_df['close'].values

            # Calculate True Range
            tr1 = high - low
            tr2 = np.abs(high - np.roll(close, 1))
            tr3 = np.abs(low - np.roll(close, 1))

            tr = np.maximum(tr1, np.maximum(tr2, tr3))

            # Remove first element (invalid due to roll)
            tr = tr[1:]

            # Calculate ATR as SMA of TR
            atr = np.mean(tr[-period:])

            return float(atr)

        except Exception as e:
            logger.error(
                "atr_calculation_error",
                error=str(e)
            )
            return None

    def update_parameters(self, updates: dict) -> dict:
        """
        PURPOSE: Apply dynamic parameter updates from Brain/LLM recommendations.

        Args:
            updates: Dict of parameter name -> new value

        Returns:
            dict: Actually applied changes {param: new_value}

        CALLED BY: engine.py via BaseStrategy.update_parameters()
        """
        applied = {}
        param_attr_map = {
            'z_score_threshold': '_z_score_threshold',
            'adx_max_threshold': '_adx_max_threshold',
            'bb_period': '_bb_period',
            'grid_levels': '_grid_levels',
            'grid_spacing_pct': '_grid_spacing_pct',
        }
        for param, new_val in updates.items():
            attr = param_attr_map.get(param)
            if attr and hasattr(self, attr):
                old_val = getattr(self, attr)
                setattr(self, attr, new_val)
                self._config[param] = new_val
                applied[param] = new_val
                logger.info(
                    "strategy_b_param_updated",
                    param=param,
                    old_value=old_val,
                    new_value=new_val,
                )
        return applied

    def get_config(self) -> dict:
        """
        PURPOSE: Return the strategy's current configuration.

        Returns a dictionary with all configurable parameters for
        persistence, external updates, or API exposure.

        Returns:
            dict: Configuration dictionary

        CALLED BY: API endpoints, configuration management
        """
        return {
            'grid_levels': self._grid_levels,
            'grid_spacing_pct': self._grid_spacing_pct,
            'lookback': self._lookback,
            'bb_period': self._bb_period,
            'z_score_threshold': self._z_score_threshold,
            'adx_max_threshold': self._adx_max_threshold,
            'timeframe': self._timeframe,
            'default_lots': self._default_lots,
        }
