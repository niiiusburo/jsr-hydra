"""
PURPOSE: Strategy E - Sideways Range Scalper for low-trend conditions.

STRATEGY LOGIC:
    - Filters for ranging/sideways markets using ADX ceiling.
    - Uses Bollinger Band extremes + RSI confirmation for mean-reversion entries.
    - BUY near lower band in weak-trend conditions.
    - SELL near upper band in weak-trend conditions.
    - Targets the middle band (or minimum ATR scalp target), with tight ATR stops.
    - Designed for higher execution frequency on M5 candles.

CALLED BY: engine/orchestrator.py -> run_cycle()
"""

from typing import Optional

import pandas as pd

from app.bridge.data_feed import DataFeed
from app.bridge.order_manager import OrderManager
from app.config.constants import OrderDirection, StrategyCode
from app.events.bus import EventBus
from app.indicators.momentum import rsi
from app.indicators.trend import adx
from app.indicators.volatility import atr, bollinger_bands
from app.strategies.base import BaseStrategy
from app.strategies.signals import StrategySignal
from app.utils.logger import get_logger


logger = get_logger("strategies.strategy_e")


class StrategyE(BaseStrategy):
    """
    PURPOSE: Sideways mean-reversion scalper for range-bound markets.

    Trades short moves from Bollinger Band extremes back toward the mean when
    trend strength (ADX) is weak.
    """

    def __init__(
        self,
        data_feed: DataFeed,
        order_manager: OrderManager,
        event_bus: EventBus,
        config: dict,
    ):
        super().__init__(
            code=StrategyCode.E,
            name="Range Scalper (Sideways)",
            data_feed=data_feed,
            order_manager=order_manager,
            event_bus=event_bus,
            config=config,
        )

        self._bb_period = config.get("bb_period", 20)
        self._bb_std = config.get("bb_std", 2.0)
        self._rsi_period = config.get("rsi_period", 9)
        self._rsi_buy = config.get("rsi_buy", 35)
        self._rsi_sell = config.get("rsi_sell", 65)
        self._adx_period = config.get("adx_period", 14)
        self._adx_max = config.get("adx_max", 20)
        self._atr_period = config.get("atr_period", 14)
        self._sl_atr_mult = config.get("sl_atr_mult", 0.8)
        self._min_tp_atr_mult = config.get("min_tp_atr_mult", 0.6)
        self._timeframe = config.get("timeframe", "M5")
        self._lookback = config.get("lookback", 120)
        self._default_lots = config.get("default_lots", 0.01)

        logger.info(
            "strategy_e_initialized",
            bb_period=self._bb_period,
            bb_std=self._bb_std,
            rsi_period=self._rsi_period,
            rsi_buy=self._rsi_buy,
            rsi_sell=self._rsi_sell,
            adx_period=self._adx_period,
            adx_max=self._adx_max,
            atr_period=self._atr_period,
            timeframe=self._timeframe,
        )

    def generate_signal(self, candles_df: pd.DataFrame) -> Optional[StrategySignal]:
        """
        Generate a scalping signal in sideways conditions.

        Conditions:
        1. ADX must be below threshold (weak trend / range).
        2. Price must be near Bollinger Band extreme (percent-b filter).
        3. RSI confirms local extension.
        4. Candle close location confirms rejection from extreme.
        """
        try:
            min_data = max(
                self._bb_period,
                self._rsi_period,
                self._adx_period,
                self._atr_period,
            ) + 10
            if len(candles_df) < min_data:
                logger.warning(
                    "insufficient_data_for_strategy_e",
                    available=len(candles_df),
                    required=min_data,
                )
                return None

            close = candles_df["close"]
            high = candles_df["high"]
            low = candles_df["low"]

            upper_band, middle_band, lower_band = bollinger_bands(
                close,
                period=self._bb_period,
                std_dev=self._bb_std,
            )
            rsi_values = rsi(close, period=self._rsi_period)
            adx_values = adx(high, low, close, period=self._adx_period)
            atr_values = atr(high, low, close, period=self._atr_period)

            latest_close = float(close.iloc[-1])
            latest_high = float(high.iloc[-1])
            latest_low = float(low.iloc[-1])
            latest_upper = float(upper_band.iloc[-1])
            latest_middle = float(middle_band.iloc[-1])
            latest_lower = float(lower_band.iloc[-1])
            latest_rsi = float(rsi_values.iloc[-1])
            latest_adx = float(adx_values.iloc[-1])
            latest_atr = float(atr_values.iloc[-1])

            if any(
                pd.isna(v)
                for v in (
                    latest_upper,
                    latest_middle,
                    latest_lower,
                    latest_rsi,
                    latest_adx,
                    latest_atr,
                )
            ):
                return None

            if latest_adx > self._adx_max:
                logger.debug(
                    "strategy_e_skipped_non_sideways",
                    adx=latest_adx,
                    adx_max=self._adx_max,
                )
                return None

            band_span = latest_upper - latest_lower
            if band_span <= 0:
                return None

            percent_b = (latest_close - latest_lower) / band_span

            candle_range = max(latest_high - latest_low, 1e-9)
            close_pos = (latest_close - latest_low) / candle_range

            buy_setup = (
                percent_b <= 0.12
                and latest_rsi <= self._rsi_buy
                and close_pos >= 0.45
            )
            sell_setup = (
                percent_b >= 0.88
                and latest_rsi >= self._rsi_sell
                and close_pos <= 0.55
            )

            if buy_setup and not sell_setup:
                direction = OrderDirection.BUY
                sl_price = min(latest_low, latest_close - (latest_atr * self._sl_atr_mult))
                tp_price = max(
                    latest_middle,
                    latest_close + (latest_atr * self._min_tp_atr_mult),
                )
                band_score = max(0.0, min(1.0, (0.12 - percent_b) / 0.12))
                rsi_score = max(0.0, min(1.0, (self._rsi_buy - latest_rsi) / 20.0))
                reason = (
                    f"Range scalp BUY: ADX {latest_adx:.1f} <= {self._adx_max}, "
                    f"%B {percent_b:.2f} near lower band, RSI {latest_rsi:.1f}."
                )
            elif sell_setup and not buy_setup:
                direction = OrderDirection.SELL
                sl_price = max(latest_high, latest_close + (latest_atr * self._sl_atr_mult))
                tp_price = min(
                    latest_middle,
                    latest_close - (latest_atr * self._min_tp_atr_mult),
                )
                band_score = max(0.0, min(1.0, (percent_b - 0.88) / 0.12))
                rsi_score = max(0.0, min(1.0, (latest_rsi - self._rsi_sell) / 20.0))
                reason = (
                    f"Range scalp SELL: ADX {latest_adx:.1f} <= {self._adx_max}, "
                    f"%B {percent_b:.2f} near upper band, RSI {latest_rsi:.1f}."
                )
            else:
                return None

            if direction == OrderDirection.BUY:
                if not (sl_price < latest_close < tp_price):
                    return None
            else:
                if not (tp_price < latest_close < sl_price):
                    return None

            adx_score = max(0.0, min(1.0, (self._adx_max - latest_adx) / max(self._adx_max, 1)))
            confidence = max(
                0.2,
                min(
                    0.95,
                    0.4 + (0.25 * adx_score) + (0.2 * band_score) + (0.15 * rsi_score),
                ),
            )

            return StrategySignal(
                direction=direction,
                confidence=round(confidence, 3),
                sl_price=float(sl_price),
                tp_price=float(tp_price),
                reason=reason,
                strategy_code=self._code.value,
            )

        except Exception as e:
            logger.error("strategy_e_generate_signal_error", error=str(e))
            return None

    def get_config(self) -> dict:
        """Return strategy configuration."""
        return {
            "bb_period": self._bb_period,
            "bb_std": self._bb_std,
            "rsi_period": self._rsi_period,
            "rsi_buy": self._rsi_buy,
            "rsi_sell": self._rsi_sell,
            "adx_period": self._adx_period,
            "adx_max": self._adx_max,
            "atr_period": self._atr_period,
            "sl_atr_mult": self._sl_atr_mult,
            "min_tp_atr_mult": self._min_tp_atr_mult,
            "timeframe": self._timeframe,
            "lookback": self._lookback,
            "default_lots": self._default_lots,
        }
