"""
PURPOSE: Main trading orchestrator engine for JSR Hydra.

The core trading loop that coordinates all components: MT5 bridge, strategies,
risk management, event system, and database. Runs continuously, checking market
conditions and executing trades via strategy signals.

CALLED BY:
    - engine/engine_runner.py (entry point)
"""

import asyncio
import json
import signal
from datetime import datetime
from typing import Optional, List, Dict

from app.config.settings import settings
from app.bridge import create_bridge
from app.bridge.connector import MT5Connector
from app.bridge.data_feed import DataFeed
from app.bridge.order_manager import OrderManager
from app.bridge.account_info import AccountInfo
from app.events.bus import EventBus, set_event_bus
from app.events.handlers import register_all_handlers
from app.db.engine import AsyncSessionLocal
from app.risk.kill_switch import KillSwitch
from app.risk.position_sizer import PositionSizer
from app.risk.risk_manager import RiskManager
from app.engine.regime_detector import RegimeDetector
from app.indicators.trend import ema, adx
from app.indicators.volatility import atr
from app.indicators.momentum import rsi
from app.strategies.base import BaseStrategy
from app.strategies.strategy_a import StrategyA
from app.strategies.strategy_b import StrategyB
from app.strategies.strategy_c import StrategyC
from app.strategies.strategy_d import StrategyD
from app.brain import get_brain
from app.utils.logger import get_logger
from app.utils import time_utils
from app.services.trade_service import TradeService
from app.services.strategy_service import StrategyService
from app.schemas.trade import TradeCreate
from app.models.account import MasterAccount
from app.models.trade import Trade as TradeModel
from sqlalchemy import select

logger = get_logger("engine.orchestrator")


TRADING_SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]

SYMBOL_CONFIGS = {
    "EURUSD": {
        "lot_size": 0.02,
        "sl_atr_mult": 1.5,
        "tp_atr_mult": 2.0,
    },
    "GBPUSD": {
        "lot_size": 0.01,
        "sl_atr_mult": 1.5,
        "tp_atr_mult": 2.0,
    },
    "USDJPY": {
        "lot_size": 0.01,
        "sl_atr_mult": 1.5,
        "tp_atr_mult": 2.0,
    },
    "XAUUSD": {
        "lot_size": 0.01,
        "sl_atr_mult": 2.0,  # Gold needs wider stops
        "tp_atr_mult": 2.5,
    },
}


class TradingEngine:
    """
    PURPOSE: Main orchestrator for the JSR Hydra trading system.

    Coordinates all components including MT5 bridge, event bus, strategies,
    risk management, and database operations. Implements the main trading loop
    that checks market conditions and executes trades based on strategy signals.

    Runs ALL 4 strategies on ALL symbols simultaneously for maximum trade
    frequency.

    CALLED BY: engine_runner.py (entry point)

    Attributes:
        settings: Configuration settings
        _bridge: MT5 bridge components (connector, data_feed, order_manager, account_info)
        _event_bus: Event bus for inter-module communication
        _regime_detector: Market regime detector
        _risk_manager: Risk management orchestrator
        _strategies: Dict of {(symbol, strategy_code): strategy_instance}
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
        self._running = False  # Used by graceful shutdown signal handlers
        self._loop_interval = 5  # 5 seconds between cycles for real trading
        self._start_time: Optional[datetime] = None
        self._symbols: List[str] = list(TRADING_SYMBOLS)
        # Track new candle detection per (symbol, timeframe) — not global
        self._last_candle_time: Dict[tuple, datetime] = {}  # {(symbol, timeframe): datetime}

        # Track open trades: mt5_ticket -> {trade_db_id, strategy_code, symbol, ...}
        self._open_trades: Dict[int, dict] = {}
        self._cached_master_id = None

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

        # Strategy pool: keyed by (symbol, strategy_code) for multi-symbol support
        self._strategies: Dict[str, BaseStrategy] = {}

        logger.info(
            "trading_engine_initialized",
            loop_interval=self._loop_interval,
            dry_run=self.settings.DRY_RUN,
            symbols=self._symbols
        )

    async def _ensure_strategies_seeded(self) -> None:
        """
        PURPOSE: Seed default strategies A, B, C, D into the DB if they don't exist.

        Called at startup before the main trading loop so that trade recording
        never fails silently due to missing strategy rows.

        CALLED BY: start()
        """
        from app.models.strategy import Strategy
        from sqlalchemy import select as sa_select

        default_strategies = [
            {"code": "A", "name": "Trend Following", "status": "active", "allocation_pct": 25.0},
            {"code": "B", "name": "Mean Reversion", "status": "active", "allocation_pct": 25.0},
            {"code": "C", "name": "Session Breakout", "status": "active", "allocation_pct": 25.0},
            {"code": "D", "name": "Momentum Scalper", "status": "active", "allocation_pct": 25.0},
        ]

        try:
            async with AsyncSessionLocal() as session:
                for strat_data in default_strategies:
                    result = await session.execute(
                        sa_select(Strategy).where(Strategy.code == strat_data["code"])
                    )
                    if not result.scalar_one_or_none():
                        strategy = Strategy(**strat_data)
                        session.add(strategy)
                        logger.info("strategy_seeded", code=strat_data["code"])
                await session.commit()
        except Exception as e:
            logger.warning("strategy_seeding_error", error=str(e))

    async def _shutdown(self) -> None:
        """
        PURPOSE: Signal handler coroutine for graceful shutdown on SIGTERM/SIGINT.

        Sets _running and _is_running to False so the main loop exits cleanly
        on the next iteration check.

        CALLED BY: Signal handlers registered in start()
        """
        logger.info("engine_shutdown_requested")
        self._running = False
        self._is_running = False

    async def start(self) -> None:
        """
        PURPOSE: Start the trading engine and main loop.

        Sequence:
        1. Connect MT5 bridge (connector.connect())
        2. Connect EventBus to Redis
        3. Register event handlers
        4. Initialize risk management components
        5. Seed default strategies into DB
        6. Register strategies
        7. Install graceful shutdown signal handlers (SIGTERM/SIGINT)
        8. Start main trading loop

        CALLED BY: engine_runner.py, main entry point
        """
        try:
            logger.info("trading_engine_starting")

            # 1. Create and connect MT5 bridge
            await self._setup_bridge()

            # 2. Connect event bus to Redis
            await self._event_bus.connect()
            # Store as the global singleton so modules calling get_event_bus()
            # share this connected instance instead of creating a separate one.
            set_event_bus(self._event_bus)
            logger.info("event_bus_connected")

            # 3. Register event handlers and start Redis subscription listener
            register_all_handlers(self._event_bus)
            asyncio.create_task(self._event_bus.subscribe_redis())
            logger.info("event_handlers_registered")

            # 4. Initialize risk management components
            self._init_risk_management()
            logger.info("risk_management_initialized")

            # Register kill switch reset handler so the engine responds to
            # KILL_SWITCH_RESET events published by the API reset endpoint.
            kill_switch_ref = self._kill_switch

            async def _handle_kill_switch_reset(payload) -> None:
                try:
                    kill_switch_ref.reset(admin_override=True)
                    logger.warning(
                        "kill_switch_reset_via_event",
                        reset_by=payload.data.get("reset_by", "unknown")
                    )
                except Exception as reset_err:
                    logger.error("kill_switch_reset_handler_failed", error=str(reset_err))

            self._event_bus.on("KILL_SWITCH_RESET", _handle_kill_switch_reset)

            # 5. Seed default strategies so trade recording never fails silently
            await self._ensure_strategies_seeded()
            logger.info("strategies_seeded")

            # 6. Register strategies
            self._register_strategies()
            logger.info("strategies_registered", count=len(self._strategies))

            # 7. Install graceful shutdown signal handlers (SIGTERM / SIGINT)
            self._running = True
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.add_signal_handler(sig, lambda: asyncio.create_task(self._shutdown()))
            logger.info("signal_handlers_registered")

            # 8. Set running flag and record start time
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

            # 8b. Recover tracking of existing MT5 positions (after restart)
            await self._recover_open_positions()

            # 9. Run main trading loop (blocking)
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
                await self._connector.disconnect()
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
                "mt5_rest_url": self.settings.MT5_REST_URL,
                "redis_url": self.settings.REDIS_URL,
                "dry_run": self.settings.DRY_RUN,
                "max_test_lots": self.settings.MAX_TEST_LOTS,
            }

            # Create bridge components
            self._connector, self._data_feed, self._order_manager, self._account_info = (
                create_bridge(bridge_settings)
            )

            # Always connect to MT5 — we need real data
            await self._connector.connect()
            logger.info("mt5_bridge_connected")

            # Resolve trading symbols: filter TRADING_SYMBOLS to those available
            try:
                available_symbols = await self._data_feed.get_symbols()
                resolved = [s for s in TRADING_SYMBOLS if s in available_symbols]
                if resolved:
                    self._symbols = resolved
                else:
                    # Fallback: keep defaults, broker may still accept them
                    logger.warning("no_trading_symbols_found_in_broker", available=available_symbols)
                logger.info("trading_symbols_resolved", symbols=self._symbols, available=len(available_symbols))
            except Exception as e:
                logger.warning("symbol_resolution_failed", error=str(e), fallback=self._symbols)

            await self._event_bus.publish(
                event_type="MT5_CONNECTED",
                data={"dry_run": self.settings.DRY_RUN, "symbols": self._symbols},
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
                order_manager=self._order_manager
            )

            # Create position sizer
            self._position_sizer = PositionSizer()

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
        PURPOSE: Initialize and register ALL 4 strategies for EACH trading symbol.

        Creates strategy instances per-symbol with symbol-specific lot sizes
        and aggressive parameters for high trade frequency.

        CALLED BY: start()
        """
        try:
            for symbol in self._symbols:
                sym_cfg = SYMBOL_CONFIGS.get(symbol, SYMBOL_CONFIGS["EURUSD"])
                lot_size = sym_cfg["lot_size"]

                # Strategy A — Trend Following (aggressive: fast EMAs, low ADX, M15, continuation)
                key_a = f"{symbol}_A"
                strategy_a = StrategyA(
                    data_feed=self._data_feed,
                    order_manager=self._order_manager,
                    event_bus=self._event_bus,
                    config={
                        'timeframe': 'M15',
                        'lookback': 200,
                        'default_lots': lot_size,
                        'ema_fast': 9,
                        'ema_slow': 21,
                        'adx_threshold': 15,
                        'allow_continuation': True,
                    }
                )
                strategy_a.start()
                self._strategies[key_a] = strategy_a

                # Strategy B — Mean Reversion Grid (loosened z-score)
                key_b = f"{symbol}_B"
                strategy_b = StrategyB(
                    data_feed=self._data_feed,
                    order_manager=self._order_manager,
                    event_bus=self._event_bus,
                    config={
                        'timeframe': 'M15',
                        'lookback': 100,
                        'default_lots': lot_size,
                        'grid_levels': 5,
                        'grid_spacing_pips': 50,
                        'z_score_threshold': 1.3,
                    }
                )
                strategy_b.start()
                self._strategies[key_b] = strategy_b

                # Strategy C — Session Breakout (much less strict)
                key_c = f"{symbol}_C"
                strategy_c = StrategyC(
                    data_feed=self._data_feed,
                    order_manager=self._order_manager,
                    event_bus=self._event_bus,
                    config={
                        'timeframe': 'M15',
                        'lookback': 100,
                        'default_lots': lot_size,
                        'lookback_bars': 12,
                        'breakout_atr_mult': 0.5,
                    }
                )
                strategy_c.start()
                self._strategies[key_c] = strategy_c

                # Strategy D — Momentum Scalper (aggressive: loose BB+RSI, M15)
                key_d = f"{symbol}_D"
                strategy_d = StrategyD(
                    data_feed=self._data_feed,
                    order_manager=self._order_manager,
                    event_bus=self._event_bus,
                    config={
                        'timeframe': 'M15',
                        'lookback': 100,
                        'default_lots': lot_size,
                        'bb_period': 14,
                        'bb_std': 1.5,
                        'rsi_oversold': 38,
                        'rsi_overbought': 62,
                    }
                )
                strategy_d.start()
                self._strategies[key_d] = strategy_d

                logger.info("strategies_registered_for_symbol", symbol=symbol, strategies=[key_a, key_b, key_c, key_d])

            logger.info("all_strategies_registered", total=len(self._strategies), strategies=list(self._strategies.keys()))

        except Exception as e:
            logger.error("strategy_registration_failed", error=str(e))
            raise

    async def _main_loop(self) -> None:
        """
        PURPOSE: Main trading loop. Runs every 5 seconds using real MT5 data.

        Multi-symbol design: iterates over ALL symbols, detects new candles
        per (symbol, timeframe), and runs ALL strategies for each symbol.

        Sequence per iteration:
        1. For each symbol: fetch tick data, H1 candles for indicators/regime
        2. Detect new candles per (symbol, timeframe)
        3. Run all strategies that have a new candle for their symbol+timeframe
        4. Enforce SL/TP on every trade (auto-calculate from ATR if missing)
        5. Log comprehensive JSON summary every cycle
        6. Sleep 5 seconds

        CALLED BY: start()
        """
        try:
            cycle_count = 0

            while self._is_running and self._running:
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

                    all_signals_summary = {}
                    all_trades = []
                    all_risk_checks = []
                    _regime_str = "UNKNOWN"
                    _regime_conf = 0

                    # ========== LOOP OVER ALL SYMBOLS ==========
                    for symbol in self._symbols:
                        sym_cfg = SYMBOL_CONFIGS.get(symbol, SYMBOL_CONFIGS["EURUSD"])

                        # --- Fetch tick data for this symbol ---
                        tick_data = {"bid": None, "ask": None, "spread": None}
                        try:
                            tick_data = await self._data_feed.get_tick(symbol)
                        except Exception as e:
                            logger.warning("tick_fetch_failed", symbol=symbol, error=str(e))

                        # Fetch H1 candles for indicator computation and regime detection
                        indicator_values = {
                            "rsi": None, "adx": None, "atr": None,
                            "ema_20": None, "ema_50": None
                        }
                        regime = None

                        try:
                            candles_h1 = await self._data_feed.get_candles(symbol, "H1", count=200)
                            if not candles_h1.empty and len(candles_h1) >= 50:
                                close = candles_h1['close']
                                high = candles_h1['high']
                                low = candles_h1['low']

                                # Compute indicators
                                rsi_vals = rsi(close, period=14)
                                adx_vals = adx(high, low, close, period=14)
                                atr_vals = atr(high, low, close, period=14)
                                ema_20 = ema(close, 20)
                                ema_50 = ema(close, 50)

                                indicator_values = {
                                    "rsi": round(float(rsi_vals.iloc[-1]), 2) if not rsi_vals.empty else None,
                                    "adx": round(float(adx_vals.iloc[-1]), 2) if not adx_vals.empty else None,
                                    "atr": round(float(atr_vals.iloc[-1]), 4) if not atr_vals.empty else None,
                                    "ema_20": round(float(ema_20.iloc[-1]), 5) if not ema_20.empty else None,
                                    "ema_50": round(float(ema_50.iloc[-1]), 5) if not ema_50.empty else None,
                                }

                                # Detect regime
                                regime = self._regime_detector.detect_regime(candles_h1)

                        except Exception as e:
                            logger.warning("candle_indicator_fetch_failed", symbol=symbol, error=str(e))

                        # --- Detect new candles per (symbol, timeframe) ---
                        # Get strategies for this symbol
                        symbol_strategies = {
                            k: v for k, v in self._strategies.items()
                            if k.startswith(f"{symbol}_")
                        }

                        # Collect unique timeframes for this symbol's strategies
                        strategy_timeframes: Dict[str, List[str]] = {}  # tf -> [strategy_keys]
                        for strat_key, strategy in symbol_strategies.items():
                            tf = strategy._config.get('timeframe', 'H1')
                            strategy_timeframes.setdefault(tf, []).append(strat_key)

                        # Fetch candles per timeframe and detect new candles per (symbol, tf)
                        new_candle_for_tf: Dict[str, bool] = {}
                        for tf in strategy_timeframes:
                            candle_key = (symbol, tf)
                            try:
                                candles_tf = await self._data_feed.get_candles(symbol, tf, count=200)
                                if not candles_tf.empty and len(candles_tf) >= 2:
                                    latest_candle_time = candles_tf.index[-1]
                                    prev_time = self._last_candle_time.get(candle_key)
                                    if prev_time is None:
                                        new_candle_for_tf[tf] = True
                                        logger.info("initial_candle_recorded", symbol=symbol, timeframe=tf, time=str(latest_candle_time))
                                    elif latest_candle_time > prev_time:
                                        new_candle_for_tf[tf] = True
                                        logger.info("new_candle_detected", symbol=symbol, timeframe=tf, time=str(latest_candle_time))
                                    else:
                                        new_candle_for_tf[tf] = False
                                    self._last_candle_time[candle_key] = latest_candle_time
                                else:
                                    new_candle_for_tf[tf] = False
                            except Exception as e:
                                logger.warning("candle_fetch_for_tf_failed", symbol=symbol, timeframe=tf, error=str(e))
                                new_candle_for_tf[tf] = False

                        # --- Run strategies for this symbol ---
                        for strat_key, strategy in symbol_strategies.items():
                            tf = strategy._config.get('timeframe', 'H1')
                            if not new_candle_for_tf.get(tf, False):
                                all_signals_summary[strat_key] = "waiting_for_candle"
                                continue

                            try:
                                if not strategy.is_active:
                                    all_signals_summary[strat_key] = "inactive"
                                    continue

                                # Run strategy cycle to get signal
                                signal = await strategy.run_cycle(symbol)

                                if signal is None:
                                    all_signals_summary[strat_key] = "no_signal"
                                    continue

                                # --- ENFORCE SL/TP: auto-calculate from ATR if missing ---
                                sl_price = signal.stop_loss
                                tp_price = signal.take_profit
                                entry_price = signal.entry_price

                                if sl_price is None or sl_price <= 0 or tp_price is None or tp_price <= 0:
                                    # Need ATR for fallback calculation
                                    fallback_atr = indicator_values.get("atr")
                                    if fallback_atr and fallback_atr > 0:
                                        if sl_price is None or sl_price <= 0:
                                            if signal.direction == "BUY":
                                                sl_price = entry_price - (fallback_atr * sym_cfg["sl_atr_mult"])
                                            else:
                                                sl_price = entry_price + (fallback_atr * sym_cfg["sl_atr_mult"])
                                            logger.warning(
                                                "sl_auto_calculated",
                                                strategy=strat_key,
                                                symbol=symbol,
                                                sl=sl_price,
                                                atr=fallback_atr
                                            )
                                        if tp_price is None or tp_price <= 0:
                                            if signal.direction == "BUY":
                                                tp_price = entry_price + (fallback_atr * sym_cfg["tp_atr_mult"])
                                            else:
                                                tp_price = entry_price - (fallback_atr * sym_cfg["tp_atr_mult"])
                                            logger.warning(
                                                "tp_auto_calculated",
                                                strategy=strat_key,
                                                symbol=symbol,
                                                tp=tp_price,
                                                atr=fallback_atr
                                            )
                                    else:
                                        logger.warning(
                                            "cannot_auto_calculate_sl_tp_no_atr",
                                            strategy=strat_key,
                                            symbol=symbol
                                        )
                                        all_signals_summary[strat_key] = "skipped_no_sl_tp"
                                        continue

                                # Final validation: SL and TP must be positive
                                if sl_price <= 0 or tp_price <= 0:
                                    logger.warning(
                                        "invalid_sl_tp_after_calculation",
                                        strategy=strat_key,
                                        symbol=symbol,
                                        sl=sl_price,
                                        tp=tp_price
                                    )
                                    all_signals_summary[strat_key] = "invalid_sl_tp"
                                    continue

                                all_signals_summary[strat_key] = {
                                    "direction": signal.direction,
                                    "entry": entry_price,
                                    "sl": sl_price,
                                    "tp": tp_price,
                                }

                                # Pre-trade risk check
                                risk_check = await self._risk_manager.pre_trade_check(
                                    symbol=signal.symbol,
                                    direction=signal.direction,
                                    sl_distance=abs(entry_price - sl_price)
                                )

                                risk_check_info = {
                                    "strategy": strat_key,
                                    "approved": risk_check.approved,
                                    "reason": risk_check.reason,
                                    "position_size": risk_check.position_size,
                                    "risk_score": risk_check.risk_score,
                                }
                                all_risk_checks.append(risk_check_info)

                                if not risk_check.approved:
                                    logger.warning(
                                        "trade_rejected_by_risk_manager",
                                        strategy=strat_key,
                                        symbol=symbol,
                                        reason=risk_check.reason,
                                        cycle=cycle_count
                                    )
                                    await self._event_bus.publish(
                                        event_type="TRADE_REJECTED",
                                        data={
                                            "strategy": strat_key,
                                            "symbol": signal.symbol,
                                            "reason": risk_check.reason
                                        },
                                        source="engine.orchestrator",
                                        severity="WARNING"
                                    )
                                    continue

                                # Execute trade via order manager (use enforced SL/TP)
                                order_result = await self._order_manager.open_position(
                                    symbol=signal.symbol,
                                    direction=signal.direction,
                                    lots=risk_check.position_size,
                                    sl=sl_price,
                                    tp=tp_price,
                                    comment=f"JSR_{strat_key}"[:31]
                                )

                                if order_result is None:
                                    logger.warning(
                                        "order_execution_failed",
                                        strategy=strat_key,
                                        symbol=signal.symbol
                                    )
                                    continue

                                trade_info = {
                                    "strategy": strat_key,
                                    "symbol": symbol,
                                    "direction": signal.direction,
                                    "lots": risk_check.position_size,
                                    "ticket": order_result.get('ticket'),
                                    "sl": sl_price,
                                    "tp": tp_price,
                                }
                                all_trades.append(trade_info)

                                # Log trade execution
                                logger.info(
                                    "trade_executed",
                                    strategy=strat_key,
                                    symbol=signal.symbol,
                                    direction=signal.direction,
                                    lots=risk_check.position_size,
                                    ticket=order_result.get('ticket'),
                                    sl=sl_price,
                                    tp=tp_price,
                                    cycle=cycle_count
                                )

                                # Publish trade opened event
                                await self._event_bus.publish(
                                    event_type="TRADE_OPENED",
                                    data={
                                        "strategy": strat_key,
                                        "symbol": signal.symbol,
                                        "direction": signal.direction,
                                        "lots": risk_check.position_size,
                                        "entry_price": order_result.get('price'),
                                        "stop_loss": sl_price,
                                        "take_profit": tp_price,
                                        "ticket": order_result.get('ticket'),
                                        "timestamp": order_result.get('time', datetime.utcnow()).isoformat()
                                    },
                                    source="engine.orchestrator",
                                    severity="INFO"
                                )

                                # Notify Brain about the trade execution
                                try:
                                    brain = get_brain()
                                    # Extract just the strategy letter (e.g. "A") from strat_key (e.g. "EURUSD_A")
                                    pure_strategy_code = strat_key.split('_')[-1] if '_' in strat_key else strat_key
                                    # Use per-symbol regime (available from the current symbol loop iteration)
                                    regime_str_for_brain = "UNKNOWN"
                                    if isinstance(regime, dict):
                                        regime_str_for_brain = regime.get("regime", "UNKNOWN")
                                    elif regime is not None and hasattr(regime, "regime"):
                                        regime_str_for_brain = regime.regime.value if hasattr(regime.regime, "value") else str(regime.regime)
                                    elif isinstance(regime, str):
                                        regime_str_for_brain = regime

                                    brain.process_trade_result({
                                        "strategy": pure_strategy_code,
                                        "symbol": signal.symbol,
                                        "direction": signal.direction,
                                        "lots": risk_check.position_size,
                                        "entry_price": order_result.get('price'),
                                        "ticket": order_result.get('ticket'),
                                        "regime_at_entry": regime_str_for_brain,
                                    })
                                except Exception as brain_err:
                                    logger.warning("brain_trade_notify_error", error=str(brain_err))

                                # --- Record trade to database ---
                                try:
                                    async with AsyncSessionLocal() as session:
                                        master_id = await self._get_or_create_master_id(session)

                                        # Extract strategy code from strat_key (format: "SYMBOL_STRATEGY_X")
                                        strategy_code = strat_key.split('_', 1)[1] if '_' in strat_key else strat_key

                                        trade_create = TradeCreate(
                                            symbol=signal.symbol,
                                            direction=signal.direction,
                                            lots=risk_check.position_size,
                                            entry_price=order_result.get('price', entry_price),
                                            stop_loss=sl_price,
                                            take_profit=tp_price,
                                            strategy_code=strategy_code,
                                            reason=f"Signal from {strat_key}"
                                        )
                                        db_trade = await TradeService.create_trade(session, master_id, trade_create)

                                        # Set mt5_ticket and status to OPEN directly on model
                                        stmt = select(TradeModel).where(TradeModel.id == db_trade.id)
                                        result = await session.execute(stmt)
                                        trade_obj = result.scalar_one()
                                        trade_obj.mt5_ticket = order_result.get('ticket')
                                        trade_obj.status = "OPEN"
                                        await session.commit()

                                        ticket = order_result.get('ticket')
                                        if ticket:
                                            self._open_trades[ticket] = {
                                                'trade_id': db_trade.id,
                                                'strategy_code': strategy_code,
                                                'symbol': signal.symbol,
                                                'direction': signal.direction,
                                                'sl': sl_price,
                                                'tp': tp_price,
                                            }

                                        logger.info("trade_recorded_to_db", trade_id=str(db_trade.id), ticket=ticket)
                                except Exception as db_err:
                                    logger.warning("trade_db_recording_failed", error=str(db_err))

                            except Exception as e:
                                all_signals_summary[strat_key] = f"error: {str(e)}"
                                logger.error(
                                    "strategy_cycle_error",
                                    strategy=strat_key,
                                    symbol=symbol,
                                    error=str(e),
                                    cycle=cycle_count
                                )
                                await self._event_bus.publish(
                                    event_type="STRATEGY_ERROR",
                                    data={
                                        "strategy": strat_key,
                                        "symbol": symbol,
                                        "error": str(e)
                                    },
                                    source="engine.orchestrator",
                                    severity="ERROR"
                                )
                                continue

                    # ========== END SYMBOL LOOP ==========

                    # --- Check for closed positions ---
                    await self._check_closed_positions()

                    # --- Fetch account info ---
                    account_summary = {"balance": None, "equity": None, "drawdown": None}
                    try:
                        balance = await self._account_info.get_balance()
                        equity = await self._account_info.get_equity()
                        drawdown = ((balance - equity) / balance * 100.0) if balance > 0 else 0.0
                        account_summary = {
                            "balance": round(balance, 2),
                            "equity": round(equity, 2),
                            "drawdown": round(drawdown, 2),
                        }
                    except Exception as e:
                        logger.warning("account_info_fetch_failed", error=str(e))

                    # --- Kill switch auto-trigger checks ---
                    try:
                        account_info = await self._connector.get_account_info()
                        if account_info:
                            ks_balance = account_info.get('balance', 0)
                            ks_equity = account_info.get('equity', 0)

                            # Check drawdown-based kill switch
                            if ks_balance > 0:
                                peak_equity = max(ks_balance, ks_equity)
                                if self._kill_switch.check_drawdown(ks_equity, peak_equity):
                                    drawdown_pct = max(0, (peak_equity - ks_equity) / peak_equity * 100)
                                    logger.critical("auto_kill_switch_drawdown", drawdown_pct=drawdown_pct)
                                    await self._kill_switch.trigger_kill_switch()

                            # Check daily loss-based kill switch
                            if ks_balance > 0 and self._risk_manager._daily_pnl < 0:
                                if self._kill_switch.check_daily_loss(self._risk_manager._daily_pnl, ks_balance):
                                    daily_loss_pct = abs(self._risk_manager._daily_pnl) / ks_balance * 100
                                    logger.critical("auto_kill_switch_daily_loss", daily_loss_pct=daily_loss_pct)
                                    await self._kill_switch.trigger_kill_switch()
                    except Exception as ks_err:
                        logger.warning("kill_switch_auto_check_failed", error=str(ks_err))

                    # --- Log comprehensive JSON summary ---
                    # Resolve regime string and confidence from the last symbol's regime object
                    if isinstance(regime, dict):
                        _regime_str = regime.get("regime", "UNKNOWN")
                        _regime_conf = regime.get("confidence", 0)
                    elif regime is not None and hasattr(regime, "regime"):
                        _regime_str = regime.regime.value if hasattr(regime.regime, "value") else str(regime.regime)
                        _regime_conf = getattr(regime, "confidence", 0)
                    else:
                        _regime_str = "UNKNOWN"
                        _regime_conf = 0

                    cycle_summary = {
                        "event": "engine_cycle",
                        "cycle": cycle_count,
                        "symbols": self._symbols,
                        "signals": all_signals_summary,
                        "risk_checks": all_risk_checks,
                        "trades": all_trades,
                        "trades_this_cycle": len(all_trades),
                        "account": account_summary,
                        # Fields required by Brain.process_cycle()
                        "symbol": self._symbols[0] if self._symbols else "XAUUSD",
                        "indicators": indicator_values,
                        "regime": _regime_str,
                        "confidence": _regime_conf,
                        "new_candle": True,
                        "bid": tick_data.get("bid", 0) if isinstance(tick_data, dict) else 0,
                        "ask": tick_data.get("ask", 0) if isinstance(tick_data, dict) else 0,
                        "spread": tick_data.get("spread", 0) if isinstance(tick_data, dict) else 0,
                    }
                    logger.info("engine_cycle", data=json.dumps(cycle_summary, default=str))

                    # ── Feed cycle data to the Brain ──
                    try:
                        brain = get_brain()
                        brain.process_cycle(cycle_summary)
                    except Exception as brain_err:
                        logger.warning("brain_process_cycle_error", error=str(brain_err))

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

    async def _get_or_create_master_id(self, session) -> 'UUID':
        """
        PURPOSE: Get or create the master account for this engine.

        Queries MasterAccount by MT5_LOGIN from settings. If not found,
        creates a new one. Caches the result for subsequent calls.

        CALLED BY: Trade recording logic in _main_loop
        """
        if self._cached_master_id:
            return self._cached_master_id

        mt5_login = getattr(self.settings, 'MT5_LOGIN', 0) or 12345

        stmt = select(MasterAccount).where(MasterAccount.mt5_login == mt5_login)
        result = await session.execute(stmt)
        master = result.scalar_one_or_none()

        if not master:
            master = MasterAccount(mt5_login=mt5_login, broker="JSR", status="RUNNING")
            session.add(master)
            await session.commit()
            await session.refresh(master)

        self._cached_master_id = master.id
        return master.id

    async def _recover_open_positions(self) -> None:
        """
        PURPOSE: On engine startup, recover tracking of existing MT5 positions
        by matching them with OPEN trades in the database.

        Without this, positions opened before a restart would never be detected
        as closed, preventing profit recording and Brain learning.

        CALLED BY: start()
        """
        try:
            mt5_positions = await self._order_manager.get_open_positions()
            if not mt5_positions:
                logger.info("position_recovery_none", message="No MT5 positions to recover")
                return

            async with AsyncSessionLocal() as session:
                # Find all OPEN trades in DB
                stmt = select(TradeModel).where(TradeModel.status == "OPEN")
                result = await session.execute(stmt)
                open_trades = result.scalars().all()

                # Build lookup by mt5_ticket
                db_by_ticket = {}
                for t in open_trades:
                    if t.mt5_ticket:
                        db_by_ticket[t.mt5_ticket] = t

                recovered = 0
                for pos in mt5_positions:
                    ticket = pos.get('ticket')
                    if ticket and ticket not in self._open_trades:
                        db_trade = db_by_ticket.get(ticket)
                        if db_trade:
                            # Recover: look up strategy code from the Strategy table
                            strategy_code = "A"  # fallback
                            if db_trade.strategy_id:
                                from app.models.strategy import Strategy
                                strat_stmt = select(Strategy).where(Strategy.id == db_trade.strategy_id)
                                strat_result = await session.execute(strat_stmt)
                                strat_obj = strat_result.scalar_one_or_none()
                                if strat_obj:
                                    strategy_code = strat_obj.code

                            self._open_trades[ticket] = {
                                'trade_id': db_trade.id,
                                'strategy_code': strategy_code,
                                'symbol': db_trade.symbol,
                                'direction': db_trade.direction,
                                'sl': float(db_trade.stop_loss or 0),
                                'tp': float(db_trade.take_profit or 0),
                            }
                            recovered += 1

                logger.info(
                    "position_recovery_complete",
                    mt5_positions=len(mt5_positions),
                    db_open_trades=len(open_trades),
                    recovered=recovered,
                    tracked=len(self._open_trades),
                )
        except Exception as e:
            logger.warning("position_recovery_failed", error=str(e))

    async def _check_closed_positions(self) -> None:
        """
        PURPOSE: Check positions and detect closures (SL/TP hit).

        DRY_RUN mode: checks current tick price against each tracked trade's
        SL/TP levels and closes the simulated position when a level is breached.

        LIVE mode: compares tracked open trades against current MT5 positions.
        For any trade no longer open in MT5, records closure in the database,
        updates strategy performance metrics, and notifies the Brain.

        CALLED BY: _main_loop (each cycle)
        """
        if not self._open_trades:
            return

        try:
            if self.settings.DRY_RUN:
                # --- DRY_RUN: detect SL/TP hits via live tick data ---
                closed_pairs = []  # list of (ticket, exit_price)

                for ticket, trade_info in list(self._open_trades.items()):
                    symbol = trade_info.get('symbol', '')
                    direction = trade_info.get('direction', 'BUY')
                    sl = trade_info.get('sl', 0)
                    tp = trade_info.get('tp', 0)

                    try:
                        tick = await self._data_feed.get_tick(symbol)
                    except Exception:
                        continue

                    if not tick:
                        continue

                    if direction == 'BUY':
                        current_price = tick.get('bid', 0.0)
                        sl_hit = bool(sl and current_price <= sl)
                        tp_hit = bool(tp and current_price >= tp)
                    else:  # SELL
                        current_price = tick.get('ask', tick.get('bid', 0.0))
                        sl_hit = bool(sl and current_price >= sl)
                        tp_hit = bool(tp and current_price <= tp)

                    if sl_hit or tp_hit:
                        self._order_manager.close_simulated_position(ticket)
                        closed_pairs.append((ticket, current_price))
                        logger.info(
                            "dry_run_sl_tp_hit",
                            ticket=ticket,
                            symbol=symbol,
                            direction=direction,
                            current_price=current_price,
                            sl=sl,
                            tp=tp,
                            sl_hit=sl_hit,
                            tp_hit=tp_hit,
                        )

                for ticket, exit_price in closed_pairs:
                    trade_info = self._open_trades.pop(ticket)
                    await self._process_closed_trade(ticket, trade_info, exit_price=exit_price)

            else:
                # --- LIVE: compare against real MT5 open positions ---
                mt5_positions = await self._order_manager.get_open_positions()
                open_tickets = {p.get('ticket') for p in mt5_positions}

                closed_tickets_live = [t for t in self._open_trades if t not in open_tickets]

                for ticket in closed_tickets_live:
                    trade_info = self._open_trades.pop(ticket)

                    # Try to get exit details from MT5 history
                    position_data = None
                    try:
                        client = await self._connector._get_client()
                        resp = await client.get(f"/history/deal", params={"ticket": ticket})
                        if resp.status_code == 200:
                            position_data = resp.json()
                    except Exception:
                        pass

                    exit_price = 0.0
                    if position_data:
                        exit_price = position_data.get('price', 0.0)

                    if not exit_price:
                        try:
                            tick = await self._data_feed.get_tick(trade_info['symbol'])
                            if trade_info['direction'] == 'BUY':
                                exit_price = tick.get('bid', 0.0)
                            else:
                                exit_price = tick.get('ask', 0.0)
                        except Exception:
                            pass

                    await self._process_closed_trade(
                        ticket, trade_info, exit_price=exit_price, position_data=position_data
                    )

        except Exception as e:
            logger.warning("position_monitoring_failed", error=str(e))

    async def _process_closed_trade(
        self,
        ticket: int,
        trade_info: dict,
        exit_price: float = 0.0,
        position_data: Optional[dict] = None,
    ) -> None:
        """
        PURPOSE: Record a detected trade closure to the database and notify components.

        Shared by both DRY_RUN and LIVE close-detection paths in
        _check_closed_positions().

        Args:
            ticket: MT5 or simulated ticket number.
            trade_info: Dict from self._open_trades (contains trade_id, strategy_code, etc.).
            exit_price: Exit price to record (0 if unknown).
            position_data: Optional raw position data from MT5 history (LIVE only).

        CALLED BY: _check_closed_positions
        """
        trade_id = trade_info['trade_id']
        strategy_code = trade_info['strategy_code']

        try:
            profit = 0.0
            commission = 0.0
            swap = 0.0

            if position_data:
                exit_price = position_data.get('price', exit_price)
                profit = position_data.get('profit', 0.0)
                commission = position_data.get('commission', 0.0)
                swap = position_data.get('swap', 0.0)

            async with AsyncSessionLocal() as session:
                stmt = select(TradeModel).where(TradeModel.id == trade_id)
                result = await session.execute(stmt)
                trade_obj = result.scalar_one_or_none()

                if trade_obj:
                    # Calculate profit from entry/exit if not provided by MT5
                    if profit == 0.0 and exit_price > 0 and trade_obj.entry_price:
                        entry_p = float(trade_obj.entry_price)
                        lots = float(trade_obj.lots or 0.01)
                        symbol = trade_info.get('symbol', '')
                        direction = trade_info.get('direction', 'BUY')

                        # Point value depends on the symbol
                        if 'JPY' in symbol:
                            pip_value = 100.0  # per lot per pip for JPY pairs
                            point_diff = exit_price - entry_p
                        elif 'XAU' in symbol:
                            pip_value = 100.0  # per lot per pip for gold
                            point_diff = exit_price - entry_p
                        else:
                            pip_value = 100000.0  # per lot for standard pairs
                            point_diff = exit_price - entry_p

                        if direction == 'SELL':
                            point_diff = -point_diff

                        profit = round(point_diff * lots * pip_value, 2)
                        logger.info(
                            "profit_calculated_from_prices",
                            entry=entry_p, exit=exit_price,
                            direction=direction, lots=lots,
                            profit=profit, symbol=symbol,
                        )

                    await TradeService.close_trade(
                        session, trade_id,
                        exit_price=exit_price,
                        profit=profit,
                        commission=commission,
                        swap=swap
                    )

                    # Update strategy performance
                    try:
                        stmt = select(TradeModel).where(TradeModel.id == trade_id)
                        result = await session.execute(stmt)
                        closed_trade = result.scalar_one_or_none()
                        if closed_trade:
                            await StrategyService.update_strategy_performance(
                                session, strategy_code, closed_trade
                            )
                    except Exception as perf_err:
                        logger.warning("strategy_perf_update_failed", error=str(perf_err))

                    # Update risk manager with closed trade P&L
                    try:
                        net_profit = profit - commission - swap
                        await self._risk_manager.post_trade_update(net_profit, trade_info.get('symbol', ''))
                    except Exception as risk_err:
                        logger.warning("post_trade_risk_update_failed", error=str(risk_err))

                    # Notify Brain about the completed trade
                    try:
                        net_profit = profit - commission - swap
                        brain = get_brain()
                        # Extract pure strategy code (e.g. "A" from "A" or "EURUSD_A")
                        pure_code = strategy_code.split('_')[-1] if '_' in strategy_code else strategy_code
                        brain.process_trade_result({
                            "strategy": pure_code,
                            "symbol": trade_info['symbol'],
                            "direction": trade_info['direction'],
                            "entry_price": trade_obj.entry_price,
                            "exit_price": exit_price,
                            "profit": net_profit,
                            "won": net_profit > 0,
                            "ticket": ticket,
                        })
                    except Exception as brain_err:
                        logger.warning("brain_close_notify_error", error=str(brain_err))

                    # Publish TRADE_CLOSED event to the event bus
                    try:
                        net_profit = profit - commission - swap
                        await self._event_bus.publish(
                            "TRADE_CLOSED",
                            data={
                                "trade_id": str(trade_id),
                                "strategy_code": strategy_code,
                                "symbol": trade_info.get("symbol"),
                                "profit": profit,
                                "net_profit": net_profit,
                            },
                            source="engine.orchestrator",
                            severity="INFO"
                        )
                    except Exception as pub_err:
                        logger.warning("trade_closed_event_publish_failed", error=str(pub_err))

                    logger.info(
                        "trade_closed_detected",
                        ticket=ticket,
                        strategy=strategy_code,
                        profit=profit,
                        exit_price=exit_price,
                    )

        except Exception as close_err:
            logger.error("trade_close_processing_failed", ticket=ticket, error=str(close_err))

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
