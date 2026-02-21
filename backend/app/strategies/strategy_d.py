"""
PURPOSE: Strategy D - Fast Momentum Scalper using BB OR RSI on M5.

STRATEGY LOGIC:
    - Generates signals when EITHER BB or RSI condition is met (OR logic)
    - Uses fast RSI(7) for quicker signals on M5 timeframe
    - BUY when price < lower_band OR RSI < oversold threshold
    - SELL when price > upper_band OR RSI > overbought threshold
    - Momentum burst detection: large candle body + high body ratio adds confidence
    - Confidence boosted when multiple conditions align (BB + RSI + momentum)
    - Stops: SL = 1.5 * ATR, TP = 2.0 * ATR
    - Designed for frequent scalping on M5 timeframe

CALLED BY: engine/orchestrator.py -> run_cycle()
"""

import numpy as np
import pandas as pd
from typing import Optional

from app.config.constants import StrategyCode, OrderDirection
from app.bridge.data_feed import DataFeed
from app.bridge.order_manager import OrderManager
from app.events.bus import EventBus
from app.indicators.volatility import bollinger_bands, atr
from app.indicators.momentum import rsi
from app.strategies.base import BaseStrategy
from app.strategies.signals import StrategySignal
from app.utils.logger import get_logger


logger = get_logger("strategies.strategy_d")


class StrategyD(BaseStrategy):
    """
    PURPOSE: Fast Momentum Scalper using Bollinger Bands OR RSI.

    Fires on EITHER BB or RSI extremes with OR logic for high signal frequency.
    Uses RSI(7) by default for fast reaction on M5 timeframe.
    Confidence scales with the number of confirming conditions.

    CALLED BY: engine/orchestrator.py
    """

    def __init__(
        self,
        data_feed: DataFeed,
        order_manager: OrderManager,
        event_bus: EventBus,
        config: dict
    ):
        super().__init__(
            code=StrategyCode.D,
            name="Momentum Scalper (BB | RSI)",
            data_feed=data_feed,
            order_manager=order_manager,
            event_bus=event_bus,
            config=config
        )

        self._bb_period = config.get('bb_period', 20)
        self._bb_std = config.get('bb_std', 2.0)
        self._rsi_period = config.get('rsi_period', 7)
        self._rsi_oversold = config.get('rsi_oversold', 35)
        self._rsi_overbought = config.get('rsi_overbought', 65)
        self._atr_period = config.get('atr_period', 14)
        self._timeframe = config.get('timeframe', 'M5')
        self._lookback = config.get('lookback', 100)

        logger.info(
            "strategy_d_initialized",
            bb_period=self._bb_period,
            bb_std=self._bb_std,
            rsi_period=self._rsi_period,
            rsi_oversold=self._rsi_oversold,
            rsi_overbought=self._rsi_overbought,
            atr_period=self._atr_period,
            timeframe=self._timeframe,
        )

    def generate_signal(self, candles_df: pd.DataFrame) -> Optional[StrategySignal]:
        """
        PURPOSE: Generate trading signal based on BB OR RSI extremes, plus momentum bursts.

        OR logic: any single condition (BB, RSI, or momentum burst) can trigger.
        Confidence scales with the number of confirming conditions:
        - 1 condition: 0.35 base
        - 2 conditions: 0.55
        - 3 conditions: 0.75+
        """
        try:
            min_data = max(self._bb_period, self._rsi_period) + 5
            if len(candles_df) < min_data:
                return None

            close = candles_df['close']
            high = candles_df['high']
            low = candles_df['low']
            open_price = candles_df['open']

            upper_band, middle_band, lower_band = bollinger_bands(
                close, period=self._bb_period, std_dev=self._bb_std
            )
            rsi_values = rsi(close, period=self._rsi_period)
            atr_values = atr(high, low, close, self._atr_period)

            latest_close = close.iloc[-1]
            latest_open = open_price.iloc[-1]
            latest_high = high.iloc[-1]
            latest_low = low.iloc[-1]
            latest_upper_band = upper_band.iloc[-1]
            latest_middle_band = middle_band.iloc[-1]
            latest_lower_band = lower_band.iloc[-1]
            latest_rsi = rsi_values.iloc[-1]
            latest_atr = atr_values.iloc[-1]

            if (pd.isna(latest_upper_band) or pd.isna(latest_lower_band) or
                pd.isna(latest_middle_band) or pd.isna(latest_rsi) or pd.isna(latest_atr)):
                return None

            # --- Check conditions ---
            bb_buy = latest_close < latest_lower_band
            bb_sell = latest_close > latest_upper_band
            rsi_buy = latest_rsi < self._rsi_oversold
            rsi_sell = latest_rsi > self._rsi_overbought

            # Momentum burst detection
            momentum_buy = False
            momentum_sell = False
            if len(candles_df) >= 6:
                current_body = abs(latest_close - latest_open)
                candle_range = latest_high - latest_low
                body_ratio = current_body / candle_range if candle_range > 0 else 0

                recent_bodies = abs(close.iloc[-6:-1] - open_price.iloc[-6:-1])
                avg_body = recent_bodies.mean()

                if current_body > 1.5 * avg_body and body_ratio > 0.6:
                    if latest_close > latest_open:
                        momentum_buy = True
                    else:
                        momentum_sell = True

            # --- OR logic: count confirming conditions ---
            buy_count = sum([bb_buy, rsi_buy, momentum_buy])
            sell_count = sum([bb_sell, rsi_sell, momentum_sell])

            buy_reasons = []
            sell_reasons = []

            if bb_buy:
                buy_reasons.append(f"price {latest_close:.5f} < lower BB {latest_lower_band:.5f}")
            if rsi_buy:
                buy_reasons.append(f"RSI({self._rsi_period}) {latest_rsi:.1f} < {self._rsi_oversold}")
            if momentum_buy:
                buy_reasons.append("momentum burst (bullish)")
            if bb_sell:
                sell_reasons.append(f"price {latest_close:.5f} > upper BB {latest_upper_band:.5f}")
            if rsi_sell:
                sell_reasons.append(f"RSI({self._rsi_period}) {latest_rsi:.1f} > {self._rsi_overbought}")
            if momentum_sell:
                sell_reasons.append("momentum burst (bearish)")

            signal_direction = None
            reasons = []

            if buy_count > 0 and sell_count == 0:
                signal_direction = OrderDirection.BUY
                reasons = buy_reasons
            elif sell_count > 0 and buy_count == 0:
                signal_direction = OrderDirection.SELL
                reasons = sell_reasons
            else:
                return None

            # SL = 1.5 * ATR, TP = 2.0 * ATR
            if signal_direction == OrderDirection.BUY:
                sl_price = latest_close - (latest_atr * 1.5)
                tp_price = latest_close + (latest_atr * 2.0)
            else:
                sl_price = latest_close + (latest_atr * 1.5)
                tp_price = latest_close - (latest_atr * 2.0)

            if sl_price <= 0 or tp_price <= 0:
                return None

            # Confidence scales with number of confirming conditions
            condition_count = buy_count if signal_direction == OrderDirection.BUY else sell_count
            base_confidence = 0.35
            confidence = min(base_confidence + (condition_count - 1) * 0.20, 0.90)
            # Boost by RSI deviation
            rsi_deviation_bonus = min(abs(latest_rsi - 50.0) / 100.0, 0.15)
            confidence = min(confidence + rsi_deviation_bonus, 0.95)

            reason_str = "Momentum scalp: " + "; ".join(reasons)
            signal = StrategySignal(
                direction=signal_direction,
                confidence=confidence,
                sl_price=sl_price,
                tp_price=tp_price,
                reason=reason_str,
                strategy_code=self._code.value
            )

            logger.info(
                "signal_generated",
                direction=signal_direction,
                confidence=round(confidence, 3),
                conditions=condition_count,
                sl=sl_price,
                tp=tp_price,
                rsi=latest_rsi,
                atr=latest_atr,
            )

            return signal

        except Exception as e:
            logger.error("generate_signal_error", error=str(e), error_type=type(e).__name__)
            return None

    def update_parameters(self, updates: dict) -> dict:
        applied = {}
        param_attr_map = {
            'bb_period': '_bb_period',
            'bb_std': '_bb_std',
            'rsi_period': '_rsi_period',
            'rsi_oversold': '_rsi_oversold',
            'rsi_overbought': '_rsi_overbought',
            'atr_period': '_atr_period',
        }
        for param, new_val in updates.items():
            attr = param_attr_map.get(param)
            if attr and hasattr(self, attr):
                old_val = getattr(self, attr)
                setattr(self, attr, new_val)
                self._config[param] = new_val
                applied[param] = new_val
                logger.info("strategy_d_param_updated", param=param, old_value=old_val, new_value=new_val)
        return applied

    def get_config(self) -> dict:
        return {
            "bb_period": self._bb_period,
            "bb_std": self._bb_std,
            "rsi_period": self._rsi_period,
            "rsi_oversold": self._rsi_oversold,
            "rsi_overbought": self._rsi_overbought,
            "atr_period": self._atr_period,
            "timeframe": self._timeframe,
            "lookback": self._lookback,
            "default_lots": self._config.get('default_lots', 1.0),
        }
