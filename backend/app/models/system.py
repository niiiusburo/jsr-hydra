from uuid import uuid4
from datetime import datetime
from typing import Optional
from sqlalchemy import Integer, String, JSON, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class EventLog(Base):
    """System event logging."""

    __tablename__ = "event_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), default="INFO")
    source_module: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default={})
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=func.now(),
        nullable=False,
        index=True
    )


class SystemHealth(Base, TimestampMixin):
    """System service health monitoring."""

    __tablename__ = "system_health"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4
    )
    service_name: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    last_heartbeat: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    metrics: Mapped[dict] = mapped_column(JSON, default={})
    version: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
