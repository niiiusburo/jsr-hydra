"""
PURPOSE: Abstract base class for all trading strategies in JSR Hydra.

Defines the BaseStrategy abstract base class that all strategies must
inherit from, ensuring consistent interface and behavior across all
strategy implementations. Handles lifecycle management, event publishing,
and trade result tracking.

CALLED BY: engine/orchestrator.py
"""

import asyncio
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional
import pandas as pd

from app.config.constants import StrategyCode, StrategyStatus
from app.bridge.data_feed import DataFeed
from app.bridge.order_manager import OrderManager
from app.events.bus import EventBus
from app.schemas.trade import TradeCreate
from app.strategies.signals import StrategySignal
from app.utils.logger import get_logger


logger = get_logger("strategies.base")


class BaseStrategy(ABC):
    """
    PURPOSE: Abstract base class for all trading strategies.

    Defines the interface that all strategies must implement and
    provides concrete methods for lifecycle management, status tracking,
    and trade recording. Strategies inherit from this class and implement
    abstract methods for signal generation and configuration.

    CALLED BY: engine/orchestrator.py → for signal generation and lifecycle

    Attributes:
        _code: Strategy code enumeration (A, B, C, D)
        _name: Human-readable strategy name
        _data_feed: DataFeed instance for accessing market data
        _order_manager: OrderManager instance for executing trades
        _event_bus: EventBus instance for publishing events
        _config: Strategy-specific configuration dictionary
        _is_active: Current operational status flag
        _trade_count: Total trades executed by this strategy
        _winning_trades: Number of winning trades
        _losing_trades: Number of losing trades
        _total_profit: Cumulative profit from all trades
    """

    def __init__(
        self,
        code: StrategyCode,
        name: str,
        data_feed: DataFeed,
        order_manager: OrderManager,
        event_bus: EventBus,
        config: dict
    ):
        """
        PURPOSE: Initialize BaseStrategy with dependencies and configuration.

        Args:
            code: StrategyCode enum value (A, B, C, D)
            name: Human-readable strategy name
            data_feed: DataFeed instance for market data access
            order_manager: OrderManager instance for trade execution
            event_bus: EventBus instance for event publishing
            config: Strategy-specific configuration dictionary

        CALLED BY: Strategy subclass constructors
        """
        self._code = code
        self._name = name
        self._data_feed = data_feed
        self._order_manager = order_manager
        self._event_bus = event_bus
        self._config = config
        self._is_active = False
        self._trade_count = 0
        self._winning_trades = 0
        self._losing_trades = 0
        self._total_profit = 0.0

        logger.info(
            "strategy_initialized",
            strategy_code=self._code.value,
            strategy_name=self._name,
            config_keys=list(config.keys())
        )

    @property
    def code(self) -> StrategyCode:
        """
        PURPOSE: Get the strategy code enumeration.

        Returns:
            StrategyCode: Strategy identifier (A, B, C, D)

        CALLED BY: engine/orchestrator.py, external modules
        """
        return self._code

    @property
    def name(self) -> str:
        """
        PURPOSE: Get the human-readable strategy name.

        Returns:
            str: Strategy name

        CALLED BY: engine/orchestrator.py, UI/API
        """
        return self._name

    @property
    def is_active(self) -> bool:
        """
        PURPOSE: Get the current operational status of the strategy.

        Returns:
            bool: True if strategy is running, False if paused/stopped

        CALLED BY: engine/orchestrator.py, status checks
        """
        return self._is_active

    def start(self) -> None:
        """
        PURPOSE: Start the strategy and begin generating signals.

        Sets is_active flag to True and publishes STRATEGY_STARTED event.
        This is called when the strategy transitions from PAUSED to ACTIVE.

        CALLED BY: engine/orchestrator.py, strategy management
        """
        if self._is_active:
            logger.warning(
                "strategy_already_active",
                strategy_code=self._code.value
            )
            return

        self._is_active = True
        logger.info(
            "strategy_started",
            strategy_code=self._code.value,
            strategy_name=self._name
        )

        try:
            asyncio.ensure_future(self._event_bus.publish(
                event_type="STRATEGY_STARTED",
                data={
                    "strategy_code": self._code.value,
                    "strategy_name": self._name,
                    "timestamp": datetime.utcnow().isoformat()
                },
                source=f"strategies.{self._code.value.lower()}"
            ))
        except Exception as e:
            logger.error(
                "failed_to_publish_strategy_started",
                strategy_code=self._code.value,
                error=str(e)
            )

    def stop(self) -> None:
        """
        PURPOSE: Stop the strategy and cease generating signals.

        Sets is_active flag to False. Strategy will not generate signals
        until start() is called again.

        CALLED BY: engine/orchestrator.py, shutdown procedures
        """
        self._is_active = False
        logger.info(
            "strategy_stopped",
            strategy_code=self._code.value,
            strategy_name=self._name
        )

    def pause(self) -> None:
        """
        PURPOSE: Pause the strategy temporarily without fully stopping it.

        Sets is_active to False but publishes STRATEGY_PAUSED event,
        allowing external systems to know why the pause occurred.

        CALLED BY: engine/orchestrator.py, risk management (drawdown hits)
        """
        if not self._is_active:
            logger.warning(
                "strategy_already_paused",
                strategy_code=self._code.value
            )
            return

        self._is_active = False
        logger.info(
            "strategy_paused",
            strategy_code=self._code.value,
            strategy_name=self._name
        )

        try:
            asyncio.ensure_future(self._event_bus.publish(
                event_type="STRATEGY_PAUSED",
                data={
                    "strategy_code": self._code.value,
                    "strategy_name": self._name,
                    "timestamp": datetime.utcnow().isoformat()
                },
                source=f"strategies.{self._code.value.lower()}"
            ))
        except Exception as e:
            logger.error(
                "failed_to_publish_strategy_paused",
                strategy_code=self._code.value,
                error=str(e)
            )

    def get_status(self) -> StrategyStatus:
        """
        PURPOSE: Get the current operational status of the strategy.

        Returns:
            StrategyStatus: ACTIVE if running, PAUSED if inactive

        CALLED BY: API endpoints, status monitoring
        """
        return StrategyStatus.ACTIVE if self._is_active else StrategyStatus.PAUSED

    def record_trade_result(self, profit: float) -> None:
        """
        PURPOSE: Record the result of a closed trade.

        Updates internal counters for total trades, winning/losing trades,
        and cumulative profit. Used by engine to track strategy performance.

        Args:
            profit: Profit or loss from the closed trade (positive or negative)

        CALLED BY: engine/orchestrator.py, after trade closure
        """
        self._trade_count += 1
        self._total_profit += profit

        if profit > 0:
            self._winning_trades += 1
        else:
            self._losing_trades += 1

        logger.info(
            "trade_result_recorded",
            strategy_code=self._code.value,
            profit=profit,
            total_trades=self._trade_count,
            total_profit=self._total_profit
        )

    def get_win_rate(self) -> float:
        """
        PURPOSE: Calculate the win rate of the strategy.

        Returns the percentage of trades that were profitable.
        Returns 0.0 if no trades have been executed yet.

        Returns:
            float: Win rate between 0.0 and 1.0

        CALLED BY: engine/orchestrator.py, meta-controller, API
        """
        if self._trade_count == 0:
            return 0.0
        return self._winning_trades / self._trade_count

    def get_profit_factor(self) -> float:
        """
        PURPOSE: Calculate the profit factor of the strategy.

        Profit factor = Total winning trades / Total losing trades.
        Values > 1.0 indicate profitability.
        Returns 0.0 if no losing trades (all winners).

        Returns:
            float: Profit factor ratio

        CALLED BY: engine/orchestrator.py, meta-controller, API
        """
        if self._losing_trades == 0:
            return float('inf') if self._winning_trades > 0 else 0.0
        return self._winning_trades / self._losing_trades

    @abstractmethod
    def generate_signal(self, candles_df: pd.DataFrame) -> Optional[StrategySignal]:
        """
        PURPOSE: Generate a trading signal based on market data analysis.

        Must be implemented by all subclasses. Analyzes the provided candles
        and returns either a StrategySignal (if conditions met) or None
        (if no tradeable setup found).

        Args:
            candles_df: DataFrame with columns [open, high, low, close, volume]
                       Index should be datetime

        Returns:
            StrategySignal: Trading signal if conditions met, or None if not

        CALLED BY: run_cycle() method
        """
        pass

    @abstractmethod
    def get_config(self) -> dict:
        """
        PURPOSE: Get the strategy's configuration dictionary.

        Must be implemented by subclasses to return their specific configuration
        parameters. Used for persistence and external configuration updates.

        Returns:
            dict: Configuration dictionary with strategy-specific parameters

        CALLED BY: API endpoints, configuration management
        """
        pass

    async def run_cycle(self, symbol: str) -> Optional[TradeCreate]:
        """
        PURPOSE: Execute one complete strategy cycle: fetch data, generate signal, return trade.

        This is the main entry point called by the orchestrator on every candle.
        Fetches the latest candles, generates a signal, and returns a TradeCreate
        schema if a signal is generated, or None if no setup found.

        Args:
            symbol: Trading symbol (e.g., "EURUSD", "GOLD")

        Returns:
            TradeCreate: Trade creation schema if signal generated, or None

        CALLED BY: engine/orchestrator.py
        """
        try:
            # Fetch latest candles for analysis
            candles_df = self._data_feed.get_candles(
                symbol=symbol,
                timeframe=self._config.get('timeframe', 'H1'),
                count=self._config.get('lookback', 50)
            )

            if candles_df.empty:
                logger.warning(
                    "no_candles_available",
                    strategy_code=self._code.value,
                    symbol=symbol
                )
                return None

            # Validate candle data quality
            if not self._data_feed.validate_candles(candles_df):
                logger.warning(
                    "candles_validation_failed",
                    strategy_code=self._code.value,
                    symbol=symbol
                )
                return None

            # Generate signal from candles
            signal = self.generate_signal(candles_df)

            if signal is None:
                logger.debug(
                    "no_signal_generated",
                    strategy_code=self._code.value,
                    symbol=symbol
                )
                return None

            # Convert signal to TradeCreate schema for execution
            trade_create = TradeCreate(
                symbol=symbol,
                direction=signal.direction,
                lots=self._config.get('default_lots', 1.0),
                entry_price=candles_df['close'].iloc[-1],
                stop_loss=signal.sl_price,
                take_profit=signal.tp_price,
                strategy_code=self._code.value,
                reason=signal.reason
            )

            logger.info(
                "signal_generated_and_converted",
                strategy_code=self._code.value,
                symbol=symbol,
                direction=signal.direction,
                confidence=signal.confidence
            )

            return trade_create

        except Exception as e:
            logger.error(
                "run_cycle_error",
                strategy_code=self._code.value,
                symbol=symbol,
                error=str(e)
            )
            return None
