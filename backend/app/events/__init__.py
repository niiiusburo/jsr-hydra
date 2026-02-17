"""
Event bus module for JSR Hydra trading system.

Provides Redis-based pub/sub event system for inter-module communication.
Exports EventBus, EventPayload, and event_bus singleton for application-wide use.
"""

from app.events.types import EventPayload
from app.events.bus import EventBus, get_event_bus

__all__ = [
    "EventBus",
    "EventPayload",
    "get_event_bus",
]
