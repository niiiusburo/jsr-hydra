"""
Event payload types for the JSR Hydra event bus system.

Defines EventPayload model and related types for structured event communication.
"""

from datetime import datetime
from uuid import uuid4

from pydantic import BaseModel, Field


class EventPayload(BaseModel):
    """
    Standardized event payload for all events in the trading system.

    PURPOSE: Ensure consistent structure for all events published to the event bus.
    USED BY: EventBus publish/subscribe operations.

    Attributes:
        event_type: Type of event (e.g., TRADE_OPENED, REGIME_CHANGED).
        source: Module or component that originated the event.
        data: Event-specific payload data as dictionary.
        timestamp: When the event was created (UTC).
        correlation_id: Unique ID for tracing related events across modules.
        severity: Event severity level (INFO, WARNING, ERROR, CRITICAL).
    """

    event_type: str = Field(
        ...,
        description="Type identifier for the event"
    )
    source: str = Field(
        ...,
        description="Module or component that generated this event"
    )
    data: dict = Field(
        default_factory=dict,
        description="Event-specific payload data"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="UTC timestamp when event was created"
    )
    correlation_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique correlation ID for tracing across modules"
    )
    severity: str = Field(
        default="INFO",
        description="Severity level: INFO, WARNING, ERROR, or CRITICAL"
    )

    class Config:
        """Pydantic model configuration."""
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
