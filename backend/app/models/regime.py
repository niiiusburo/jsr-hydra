from uuid import uuid4
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Float, Integer, Boolean, JSON, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class RegimeState(Base, TimestampMixin):
    """Market regime detection and state tracking."""

    __tablename__ = "regime_states"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4
    )
    regime: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    conviction_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    hmm_state: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_drifting: Mapped[bool] = mapped_column(Boolean, default=False)
    layer_scores: Mapped[dict] = mapped_column(JSON, default={})
    detected_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=func.now(),
        nullable=False,
        index=True
    )
