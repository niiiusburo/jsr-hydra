"""
Event handlers for JSR Hydra trading system events.

Provides handler functions for various trading system events including trade
execution, regime changes, and system alerts.
"""

from typing import Callable

from app.config.constants import EventType
from app.events.types import EventPayload
from app.utils.logger import get_logger


async def handle_trade_event(payload: EventPayload) -> None:
    """
    Handle trade-related events (opened, closed, modified).

    PURPOSE: Log trade events for audit trail and real-time monitoring.

    CALLED BY: EventBus on TRADE_OPENED, TRADE_CLOSED, TRADE_MODIFIED events.

    Args:
        payload: EventPayload containing trade details.

    Returns:
        None
    """
    logger = get_logger("events.handlers")
    logger.info(
        "trade_event",
        event_type=payload.event_type,
        source=payload.source,
        data=payload.data,
        correlation_id=payload.correlation_id
    )


async def handle_regime_event(payload: EventPayload) -> None:
    """
    Handle market regime change events.

    PURPOSE: Log regime transitions with confidence metrics for strategy
    adaptation and performance analysis.

    CALLED BY: EventBus on REGIME_CHANGED event.

    Args:
        payload: EventPayload containing regime and confidence data.

    Returns:
        None
    """
    logger = get_logger("events.handlers")
    logger.info(
        "regime_event",
        regime=payload.data.get("regime"),
        confidence=payload.data.get("confidence"),
        source=payload.source,
        correlation_id=payload.correlation_id
    )


async def handle_system_event(payload: EventPayload) -> None:
    """
    Handle critical system events with alerting for high-severity events.

    PURPOSE: Log system events and trigger notifications (e.g., Telegram alerts)
    for critical issues requiring immediate attention.

    CALLED BY: EventBus on system-level events (kill switch, connection loss,
    strategy errors, etc.).

    Args:
        payload: EventPayload containing system event details.

    Returns:
        None
    """
    logger = get_logger("events.handlers")
    logger.info(
        "system_event",
        event_type=payload.event_type,
        severity=payload.severity,
        source=payload.source,
        data=payload.data,
        correlation_id=payload.correlation_id
    )

    # Send Telegram notification for high-severity events
    if payload.severity in ("ERROR", "CRITICAL"):
        logger.warning(
            "should_send_telegram",
            event_type=payload.event_type,
            severity=payload.severity,
            correlation_id=payload.correlation_id
        )
        # TODO: Implement Telegram notification integration
        # from app.integrations.telegram import notify_alert
        # await notify_alert(f"{payload.event_type}: {payload.data}")


async def handle_trade_closed_update_strategy(payload: EventPayload) -> None:
    """
    Update strategy performance metrics when a trade closes.

    PURPOSE: Recalculate win_rate, profit_factor, total_trades after each closed trade.

    CALLED BY: EventBus on TRADE_CLOSED event.
    """
    logger = get_logger("events.handlers")

    try:
        trade_data = payload.data
        strategy_code = trade_data.get("strategy_code")

        if not strategy_code:
            return

        from app.db.engine import AsyncSessionLocal
        from app.services.strategy_service import StrategyService
        from app.models.trade import Trade
        from sqlalchemy import select

        async with AsyncSessionLocal() as session:
            # Get the trade
            trade_id = trade_data.get("trade_id")
            if trade_id:
                stmt = select(Trade).where(Trade.id == trade_id)
                result = await session.execute(stmt)
                trade = result.scalar_one_or_none()
                if trade:
                    await StrategyService.update_strategy_performance(session, strategy_code, trade)
                    logger.info("strategy_performance_updated_from_event", strategy_code=strategy_code)
    except Exception as e:
        logger.error("handle_trade_closed_update_strategy_error", error=str(e))


def register_all_handlers(bus) -> None:
    """
    Wire up all event handlers to the event bus.

    PURPOSE: Centralize event handler registration during application
    initialization to ensure all system events are properly monitored.

    CALLED BY: Application startup sequence.

    Args:
        bus: EventBus instance to register handlers with.

    Returns:
        None
    """
    logger = get_logger("events.handlers")

    # Trade event handlers
    bus.on(EventType.TRADE_OPENED.value, handle_trade_event)
    bus.on(EventType.TRADE_CLOSED.value, handle_trade_event)
    bus.on(EventType.TRADE_CLOSED.value, handle_trade_closed_update_strategy)
    bus.on(EventType.TRADE_MODIFIED.value, handle_trade_event)

    # Regime event handlers
    bus.on(EventType.REGIME_CHANGED.value, handle_regime_event)

    # System event handlers
    bus.on(EventType.KILL_SWITCH_TRIGGERED.value, handle_system_event)
    bus.on(EventType.DAILY_LIMIT_HIT.value, handle_system_event)
    bus.on(EventType.WEEKLY_LIMIT_HIT.value, handle_system_event)
    bus.on(EventType.MONTHLY_LIMIT_HIT.value, handle_system_event)
    bus.on(EventType.MT5_CONNECTED.value, handle_system_event)
    bus.on(EventType.MT5_DISCONNECTED.value, handle_system_event)
    bus.on(EventType.MT5_CONNECTION_ERROR.value, handle_system_event)
    bus.on(EventType.STRATEGY_ERROR.value, handle_system_event)
    bus.on(EventType.SYSTEM_ERROR.value, handle_system_event)
    bus.on(EventType.HEARTBEAT_MISSED.value, handle_system_event)
    bus.on(EventType.CONFIGURATION_CHANGED.value, handle_system_event)

    logger.info("all_handlers_registered")
