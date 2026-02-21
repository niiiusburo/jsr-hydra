"""
Redis-based event bus for JSR Hydra trading system.

Provides pub/sub event system for inter-module communication with support for
both Redis distribution and local handler registration.
"""

import json
from typing import Callable, Optional

import redis.asyncio as redis

from app.events.types import EventPayload
from app.utils.logger import get_logger


class EventBus:
    """
    Redis pub/sub event bus for trading system events.

    PURPOSE: Enable asynchronous, decoupled communication between system modules
    using Redis pub/sub with local handler fallback support.

    CALLED BY: All modules that need to publish or subscribe to trading events.

    Attributes:
        CHANNEL: Redis channel name for all events.
        _redis: Async Redis client instance.
        _redis_url: Redis connection URL.
        _logger: Logger instance.
        _handlers: Registry of local event handlers by event type.
    """

    CHANNEL: str = "jsr:events"

    def __init__(self, redis_url: str) -> None:
        """
        Initialize Redis pub/sub event bus for inter-module communication.

        Args:
            redis_url: Redis connection URL (e.g., 'redis://localhost:6379').
        """
        self._redis_url: str = redis_url
        self._redis: Optional[redis.Redis] = None
        self._logger = get_logger("events.bus")
        self._handlers: dict[str, list[Callable]] = {}

    async def connect(self) -> None:
        """
        Establish Redis connection.

        Creates an async Redis client for pub/sub operations.
        Should be called during application startup.
        """
        try:
            self._redis = redis.from_url(self._redis_url, decode_responses=True)
            await self._redis.ping()
            self._logger.info("redis_connected", redis_url=self._redis_url)
        except Exception as e:
            self._logger.error("redis_connection_failed", error=str(e))
            raise

    async def disconnect(self) -> None:
        """
        Close Redis connection.

        Safely closes the Redis client connection.
        Should be called during application shutdown.
        """
        if self._redis:
            try:
                await self._redis.aclose()
                self._logger.info("redis_disconnected")
            except Exception as e:
                self._logger.error("redis_disconnection_failed", error=str(e))

    async def publish(
        self,
        event_type: str,
        data: dict,
        source: str = "unknown",
        severity: str = "INFO"
    ) -> None:
        """
        Publish event to Redis channel and invoke local handlers.

        PURPOSE: Distribute events across the system via Redis pub/sub and
        simultaneously trigger registered local handlers.

        CALLED BY: Any module requiring event distribution (trades, regime changes, etc.).

        Args:
            event_type: Type of event being published.
            data: Event payload dictionary.
            source: Module/component originating the event.
            severity: Event severity level (INFO, WARNING, ERROR, CRITICAL).

        Returns:
            None
        """
        payload = EventPayload(
            event_type=event_type,
            source=source,
            data=data,
            severity=severity
        )

        # Publish to Redis
        if self._redis:
            try:
                await self._redis.publish(self.CHANNEL, payload.model_dump_json())
                self._logger.info(
                    "event_published",
                    event_type=event_type,
                    source=source,
                    correlation_id=payload.correlation_id
                )
            except Exception as e:
                self._logger.error("redis_publish_failed", event_type=event_type, error=str(e))

        # Invoke local handlers
        for handler in self._handlers.get(event_type, []):
            try:
                await handler(payload)
            except Exception as e:
                self._logger.error(
                    "handler_error",
                    event_type=event_type,
                    error=str(e),
                    correlation_id=payload.correlation_id
                )

    async def publish_and_log(
        self,
        event_type: str,
        data: dict,
        source: str,
        severity: str,
        db_session
    ) -> None:
        """
        Publish event to Redis AND persist to event_log database table.

        PURPOSE: Ensure event is both distributed via pub/sub and permanently
        logged for audit trail and historical analysis.

        CALLED BY: Critical modules requiring full event audit trail.

        Args:
            event_type: Type of event being published.
            data: Event payload dictionary.
            source: Module/component originating the event.
            severity: Event severity level.
            db_session: SQLAlchemy async session for database persistence.

        Returns:
            None
        """
        # First publish to Redis and local handlers
        await self.publish(event_type, data, source, severity)

        # Then persist to database
        try:
            from app.models.system import EventLog
            event = EventLog(
                event_type=event_type,
                severity=severity,
                source_module=source,
                payload=data
            )
            db_session.add(event)
            await db_session.commit()
            self._logger.info(
                "event_logged",
                event_type=event_type,
                source=source
            )
        except Exception as e:
            self._logger.error("event_log_persistence_failed", error=str(e))
            await db_session.rollback()
            raise

    def on(self, event_type: str, handler: Callable) -> None:
        """
        Register a handler for an event type.

        PURPOSE: Enable modules to subscribe to specific event types without
        needing direct Redis pub/sub management.

        CALLED BY: Application initialization, module registration.

        Args:
            event_type: Event type to subscribe to.
            handler: Async callable(EventPayload) -> None.

        Returns:
            None
        """
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)
        self._logger.info("handler_registered", event_type=event_type)

    async def subscribe_redis(self) -> None:
        """
        Listen to Redis channel and dispatch to registered handlers.

        PURPOSE: Enable this process to receive events published by other
        processes via Redis pub/sub.

        CALLED BY: Application event loop during startup.

        This coroutine runs indefinitely, listening for messages on the
        shared Redis channel and invoking appropriate handlers.

        Returns:
            None (runs indefinitely until application shutdown).
        """
        if not self._redis:
            self._logger.warning("redis_not_connected_cannot_subscribe")
            return

        try:
            pubsub = self._redis.pubsub()
            await pubsub.subscribe(self.CHANNEL)
            self._logger.info("redis_subscription_started", channel=self.CHANNEL)

            async for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        payload = EventPayload.model_validate_json(message["data"])
                        for handler in self._handlers.get(payload.event_type, []):
                            try:
                                await handler(payload)
                            except Exception as e:
                                self._logger.error(
                                    "handler_error",
                                    event_type=payload.event_type,
                                    error=str(e),
                                    correlation_id=payload.correlation_id
                                )
                    except Exception as e:
                        self._logger.error("message_parsing_failed", error=str(e))
        except Exception as e:
            self._logger.error("redis_subscription_error", error=str(e))
            raise


# Global event bus singleton
_bus: Optional[EventBus] = None


def set_event_bus(bus: EventBus) -> None:
    """
    Store a connected EventBus instance as the global singleton.

    PURPOSE: Allow the engine and API server to inject the already-connected
    EventBus so that all modules (KillSwitch, TradeService, etc.) that call
    get_event_bus() receive the same connected instance rather than an
    unconnected duplicate.

    CALLED BY: engine.start() and main.py on_startup() after connecting.

    Args:
        bus: A connected EventBus instance to store as the global singleton.
    """
    global _bus
    _bus = bus


def get_event_bus() -> EventBus:
    """
    Get or create the global EventBus singleton.

    PURPOSE: Provide lazy initialization of the event bus with settings from
    the application configuration. Returns the connected instance if one has
    been set via set_event_bus(); otherwise creates a new unconnected instance.

    CALLED BY: Any module that needs the event bus.

    Returns:
        EventBus: Global singleton instance.

    Raises:
        Exception: If Redis connection fails during initialization.
    """
    global _bus
    if _bus is None:
        try:
            from app.config.settings import settings
            _bus = EventBus(settings.REDIS_URL)
        except Exception as e:
            from app.utils.logger import get_logger
            logger = get_logger("events.bus")
            logger.error("event_bus_initialization_failed", error=str(e))
            raise
    return _bus
