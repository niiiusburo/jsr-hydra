"""
Event handlers for JSR Hydra trading system events.

Provides handler functions for various trading system events including trade
execution, regime changes, and system alerts.
"""

from typing import Callable

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
    bus.on("TRADE_OPENED", handle_trade_event)
    bus.on("TRADE_CLOSED", handle_trade_event)
    bus.on("TRADE_MODIFIED", handle_trade_event)

    # Regime event handlers
    bus.on("REGIME_CHANGED", handle_regime_event)

    # System event handlers
    bus.on("KILL_SWITCH_TRIGGERED", handle_system_event)
    bus.on("DAILY_LIMIT_HIT", handle_system_event)
    bus.on("WEEKLY_LIMIT_HIT", handle_system_event)
    bus.on("MONTHLY_LIMIT_HIT", handle_system_event)
    bus.on("MT5_CONNECTED", handle_system_event)
    bus.on("MT5_DISCONNECTED", handle_system_event)
    bus.on("MT5_CONNECTION_ERROR", handle_system_event)
    bus.on("STRATEGY_ERROR", handle_system_event)
    bus.on("SYSTEM_ERROR", handle_system_event)
    bus.on("HEARTBEAT_MISSED", handle_system_event)
    bus.on("CONFIGURATION_CHANGED", handle_system_event)

    logger.info("all_handlers_registered")
