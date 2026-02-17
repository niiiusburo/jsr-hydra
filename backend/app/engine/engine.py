"""
PURPOSE: Main trading orchestrator engine for JSR Hydra.

The core trading loop that coordinates all components: MT5 bridge, strategies,
risk management, event system, and database. Runs continuously, checking market
conditions and executing trades via strategy signals.

CALLED BY:
    - engine/engine_runner.py (entry point)
"""

import asyncio
import signal
from datetime import datetime
from typing import Optional, List, Dict

from app.config.settings import settings
from app.bridge import create_bridge
from app.bridge.connector import MT5Connector
from app.bridge.data_feed import DataFeed
from app.bridge.order_manager import OrderManager
from app.bridge.account_info import AccountInfo
from app.events.bus import EventBus
from app.events.handlers import register_all_handlers
from app.db.engine import AsyncSessionLocal
from app.risk.kill_switch import KillSwitch
from app.risk.position_sizer import PositionSizer
from app.risk.risk_manager import RiskManager
from app.engine.regime_detector import RegimeDetector
from app.strategies.base import BaseStrategy
from app.strategies.strategy_b import StrategyB
from app.utils.logger import get_logger
from app.utils import time_utils

logger = get_logger("engine.orchestrator")


class TradingEngine:
    """
    PURPOSE: Main orchestrator for the JSR Hydra trading system.

    Coordinates all components including MT5 bridge, event bus, strategies,
    risk management, and database operations. Implements the main trading loop
    that checks market conditions and executes trades based on strategy signals.

    CALLED BY: engine_runner.py (entry point)

    Attributes:
        settings: Configuration settings
        _bridge: MT5 bridge components (connector, data_feed, order_manager, account_info)
        _event_bus: Event bus for inter-module communication
        _regime_detector: Market regime detector
        _risk_manager: Risk management orchestrator
        _strategies: Dictionary of active strategies
        _is_running: Flag indicating if engine is running
        _loop_interval: Interval in seconds between main loop iterations
        _start_time: Timestamp when engine started
    """

    def __init__(self, settings_obj: settings.__class__ = None):
        """
        PURPOSE: Initialize TradingEngine with settings and components.

        Args:
            settings_obj: Optional Settings object (uses global if not provided)

        CALLED BY: engine_runner.py
        """
        self.settings = settings_obj or settings
        self._is_running = False
        self._loop_interval = self.settings.__dict__.get('ENGINE_LOOP_INTERVAL', 60)
        self._start_time: Optional[datetime] = None

        # Initialize bridge components
        self._bridge = None
        self._connector: Optional[MT5Connector] = None
        self._data_feed: Optional[DataFeed] = None
        self._order_manager: Optional[OrderManager] = None
        self._account_info: Optional[AccountInfo] = None

        # Initialize event bus
        self._event_bus = EventBus(self.settings.REDIS_URL)

        # Initialize regime detector
        self._regime_detector = RegimeDetector(adx_threshold=25.0)

        # Initialize risk management components (placeholder, no initial values)
        self._kill_switch: Optional[KillSwitch] = None
        self._position_sizer: Optional[PositionSizer] = None
        self._risk_manager: Optional[RiskManager] = None

        # Strategy pool
        self._strategies: Dict[str, BaseStrategy] = {}

        logger.info(
            "trading_engine_initialized",
            loop_interval=self._loop_interval,
            dry_run=self.settings.DRY_RUN
        )

    async def start(self) -> None:
        """
        PURPOSE: Start the trading engine and main loop.

        Sequence:
        1. Connect MT5 bridge (connector.connect())
        2. Connect EventBus to Redis
        3. Register event handlers
        4. Initialize risk management components
        5. Register strategies
        6. Start main trading loop
        7. Handle signals (SIGINT, SIGTERM) for graceful shutdown

        CALLED BY: engine_runner.py, main entry point
        """
        try:
            logger.info("trading_engine_starting")

            # 1. Create and connect MT5 bridge
            await self._setup_bridge()

            # 2. Connect event bus to Redis
            await self._event_bus.connect()
            logger.info("event_bus_connected")

            # 3. Register event handlers
            register_all_handlers(self._event_bus)
            logger.info("event_handlers_registered")

            # 4. Initialize risk management components
            self._init_risk_management()
            logger.info("risk_management_initialized")

            # 5. Register strategies
            self._register_strategies()
            logger.info("strategies_registered", count=len(self._strategies))

            # 6. Set running flag and record start time
            self._is_running = True
            self._start_time = datetime.utcnow()

            # Publish engine started event
            await self._event_bus.publish(
                event_type="ENGINE_STARTED",
                data={
                    "timestamp": self._start_time.isoformat(),
                    "dry_run": self.settings.DRY_RUN
                },
                source="engine.orchestrator",
                severity="INFO"
            )

            logger.info(
                "trading_engine_started",
                time=self._start_time.isoformat(),
                strategies=len(self._strategies)
            )

            # 7. Run main trading loop (blocking)
            await self._main_loop()

        except Exception as e:
            logger.error("trading_engine_startup_failed", error=str(e))
            await self.stop()
            raise

    async def stop(self) -> None:
        """
        PURPOSE: Graceful shutdown of the trading engine.

        Sequence:
        1. Set running flag to False
        2. Stop all strategies
        3. Close all open positions (optional, for risk management)
        4. Close MT5 bridge connection
        5. Disconnect EventBus from Redis
        6. Record final state and uptime

        CALLED BY: Signal handlers, error conditions, or explicit shutdown
        """
        try:
            logger.info("trading_engine_stopping")

            # Stop running flag
            self._is_running = False

            # Stop all strategies
            for strategy_code, strategy in self._strategies.items():
                try:
                    strategy.stop()
                    logger.info("strategy_stopped", code=strategy_code)
                except Exception as e:
                    logger.error(
                        "strategy_stop_error",
                        code=strategy_code,
                        error=str(e)
                    )

            # Publish shutdown event
            uptime = self.uptime_seconds
            await self._event_bus.publish(
                event_type="ENGINE_STOPPED",
                data={
                    "timestamp": datetime.utcnow().isoformat(),
                    "uptime_seconds": uptime
                },
                source="engine.orchestrator",
                severity="INFO"
            )

            # Disconnect bridge
            if self._connector:
                self._connector.disconnect()
                logger.info("mt5_bridge_disconnected")

            # Disconnect event bus
            await self._event_bus.disconnect()
            logger.info("event_bus_disconnected")

            logger.info(
                "trading_engine_stopped",
                uptime_seconds=uptime
            )

        except Exception as e:
            logger.error("trading_engine_shutdown_error", error=str(e))

    async def _setup_bridge(self) -> None:
        """
        PURPOSE: Initialize and connect the MT5 bridge.

        Creates bridge components (connector, data_feed, order_manager, account_info)
        from factory function and establishes MT5 connection.

        CALLED BY: start()
        """
        try:
            bridge_settings = {
                "host": self.settings.MT5_HOST,
                "port": self.settings.MT5_RPYC_PORT,
                "login": self.settings.MT5_LOGIN,
                "password": self.settings.MT5_PASSWORD,
                "server": self.settings.MT5_SERVER,
                "redis_url": self.settings.REDIS_URL,
                "dry_run": self.settings.DRY_RUN,
            }

            # Create bridge components
            self._connector, self._data_feed, self._order_manager, self._account_info = (
                create_bridge(bridge_settings)
            )

            # Connect MT5 (unless in dry-run mode)
            if not self.settings.DRY_RUN:
                self._connector.connect()
                logger.info("mt5_bridge_connected")
            else:
                logger.info("mt5_bridge_initialized_dry_run_mode")

            await self._event_bus.publish(
                event_type="MT5_CONNECTED",
                data={"dry_run": self.settings.DRY_RUN},
                source="engine.orchestrator",
                severity="INFO"
            )

        except Exception as e:
            logger.error("bridge_setup_failed", error=str(e))
            raise

    def _init_risk_management(self) -> None:
        """
        PURPOSE: Initialize risk management components.

        Creates and configures kill switch, position sizer, and risk manager.

        CALLED BY: start()
        """
        try:
            # Create kill switch
            self._kill_switch = KillSwitch(
                max_drawdown_pct=self.settings.MAX_DRAWDOWN_PCT,
                account_info=self._account_info
            )

            # Create position sizer
            self._position_sizer = PositionSizer(
                account_info=self._account_info,
                risk_per_trade_pct=self.settings.RISK_PER_TRADE_PCT
            )

            # Create risk manager
            self._risk_manager = RiskManager(
                kill_switch=self._kill_switch,
                position_sizer=self._position_sizer,
                account_info=self._account_info
            )

            logger.info("risk_management_components_initialized")

        except Exception as e:
            logger.error("risk_management_init_failed", error=str(e))
            raise

    def _register_strategies(self) -> None:
        """
        PURPOSE: Initialize and register all active strategies.

        Creates strategy instances and adds them to the strategy pool.
        In Phase 1, only Strategy B is available. Phase 2+ will add A, C, D.

        CALLED BY: start()
        """
        try:
            # Strategy B (always active in Phase 1)
            strategy_b = StrategyB(
                data_feed=self._data_feed,
                order_manager=self._order_manager,
                event_bus=self._event_bus,
                config={
                    'timeframe': 'M15',
                    'lookback': 100,
                    'default_lots': 1.0,
                    'grid_levels': 5,
                    'grid_spacing_pips': 50,
                }
            )
            strategy_b.start()
            self._strategies['B'] = strategy_b

            logger.info("strategies_registered", strategies=list(self._strategies.keys()))

        except Exception as e:
            logger.error("strategy_registration_failed", error=str(e))
            raise

    async def _main_loop(self) -> None:
        """
        PURPOSE: Main trading loop. Runs continuously every N seconds.

        Sequence per iteration:
        1. Check if market is open (time_utils.is_market_open)
        2. Check if weekend (time_utils.is_weekend) → skip if true
        3. For each active strategy:
           a. Call strategy.run_cycle() to get signal
           b. If signal, pass through risk_manager.pre_trade_check()
           c. If approved, execute via order_manager.open_position()
           d. Post-trade: update daily P&L, log event
        4. Sleep interval (configurable, default 60 seconds)
        5. Heartbeat logging every cycle

        CALLED BY: start()
        """
        try:
            cycle_count = 0

            while self._is_running:
                cycle_count += 1
                cycle_start = datetime.utcnow()

                try:
                    # Check market hours
                    if not time_utils.is_market_open():
                        logger.debug(
                            "market_closed",
                            cycle=cycle_count,
                            weekday=cycle_start.weekday()
                        )
                        await asyncio.sleep(self._loop_interval)
                        continue

                    # Check for weekend
                    if time_utils.is_weekend():
                        logger.debug(
                            "weekend_detected",
                            cycle=cycle_count
                        )
                        await asyncio.sleep(self._loop_interval)
                        continue

                    # Detect current market regime
                    try:
                        regime_data = self._data_feed.get_candles("XAUUSD", "H1", count=50)
                        regime = self._regime_detector.detect_regime(regime_data)
                        logger.debug(
                            "regime_detected",
                            regime=regime['regime'].value,
                            confidence=regime['confidence']
                        )
                    except Exception as e:
                        logger.warning("regime_detection_failed", error=str(e))
                        regime = None

                    # Process each active strategy
                    for strategy_code, strategy in self._strategies.items():
                        try:
                            if not strategy.is_active:
                                logger.debug(
                                    "strategy_inactive",
                                    code=strategy_code
                                )
                                continue

                            # Run strategy cycle to get signal
                            signal = await strategy.run_cycle("XAUUSD")

                            if signal is None:
                                logger.debug(
                                    "no_signal_generated",
                                    strategy=strategy_code,
                                    cycle=cycle_count
                                )
                                continue

                            # Pre-trade risk check
                            risk_check = await self._risk_manager.pre_trade_check(
                                symbol=signal.symbol,
                                direction=signal.direction,
                                sl_distance=abs(signal.entry_price - signal.stop_loss)
                            )

                            if not risk_check.approved:
                                logger.warning(
                                    "trade_rejected_by_risk_manager",
                                    strategy=strategy_code,
                                    reason=risk_check.reason,
                                    cycle=cycle_count
                                )
                                await self._event_bus.publish(
                                    event_type="TRADE_REJECTED",
                                    data={
                                        "strategy": strategy_code,
                                        "symbol": signal.symbol,
                                        "reason": risk_check.reason
                                    },
                                    source="engine.orchestrator",
                                    severity="WARNING"
                                )
                                continue

                            # Execute trade via order manager
                            order_result = self._order_manager.open_position(
                                symbol=signal.symbol,
                                direction=signal.direction,
                                lots=risk_check.position_size,
                                sl=signal.stop_loss,
                                tp=signal.take_profit,
                                comment=f"Strategy {strategy_code}: {signal.reason}"
                            )

                            if order_result is None:
                                logger.warning(
                                    "order_execution_failed",
                                    strategy=strategy_code,
                                    symbol=signal.symbol
                                )
                                continue

                            # Log trade execution
                            logger.info(
                                "trade_executed",
                                strategy=strategy_code,
                                symbol=signal.symbol,
                                direction=signal.direction,
                                lots=risk_check.position_size,
                                ticket=order_result['ticket'],
                                cycle=cycle_count
                            )

                            # Publish trade opened event
                            await self._event_bus.publish(
                                event_type="TRADE_OPENED",
                                data={
                                    "strategy": strategy_code,
                                    "symbol": signal.symbol,
                                    "direction": signal.direction,
                                    "lots": risk_check.position_size,
                                    "entry_price": order_result['price'],
                                    "stop_loss": signal.stop_loss,
                                    "take_profit": signal.take_profit,
                                    "ticket": order_result['ticket'],
                                    "timestamp": order_result['time'].isoformat()
                                },
                                source="engine.orchestrator",
                                severity="INFO"
                            )

                        except Exception as e:
                            logger.error(
                                "strategy_cycle_error",
                                strategy=strategy_code,
                                error=str(e),
                                cycle=cycle_count
                            )
                            # Don't let one strategy crash the engine
                            await self._event_bus.publish(
                                event_type="STRATEGY_ERROR",
                                data={
                                    "strategy": strategy_code,
                                    "error": str(e)
                                },
                                source="engine.orchestrator",
                                severity="ERROR"
                            )
                            continue

                    # Heartbeat logging
                    cycle_duration = (datetime.utcnow() - cycle_start).total_seconds()
                    logger.debug(
                        "engine_cycle_completed",
                        cycle=cycle_count,
                        duration_seconds=cycle_duration,
                        strategies=len([s for s in self._strategies.values() if s.is_active])
                    )

                except Exception as e:
                    logger.error(
                        "main_loop_iteration_error",
                        cycle=cycle_count,
                        error=str(e)
                    )
                    await self._event_bus.publish(
                        event_type="SYSTEM_ERROR",
                        data={
                            "module": "engine.orchestrator",
                            "error": str(e),
                            "cycle": cycle_count
                        },
                        source="engine.orchestrator",
                        severity="ERROR"
                    )

                # Sleep before next iteration
                await asyncio.sleep(self._loop_interval)

        except Exception as e:
            logger.error("main_loop_fatal_error", error=str(e))
            raise

    @property
    def is_running(self) -> bool:
        """
        PURPOSE: Check if engine is currently running.

        Returns:
            bool: True if engine is active, False otherwise

        CALLED BY: External monitoring, status checks
        """
        return self._is_running

    @property
    def uptime_seconds(self) -> int:
        """
        PURPOSE: Calculate engine uptime in seconds.

        Returns:
            int: Number of seconds since engine started (0 if not running)

        CALLED BY: Status reporting, metrics collection
        """
        if self._start_time is None:
            return 0
        return int((datetime.utcnow() - self._start_time).total_seconds())

    @property
    def strategies(self) -> Dict[str, BaseStrategy]:
        """
        PURPOSE: Get dictionary of registered strategies.

        Returns:
            Dict[str, BaseStrategy]: Mapping of strategy code to instance

        CALLED BY: API endpoints, monitoring
        """
        return self._strategies
