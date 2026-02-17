from uuid import uuid4
from typing import Optional, List
from sqlalchemy import String, Float, Integer, Text, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Strategy(Base, TimestampMixin):
    """Trading strategy configuration and performance metrics."""

    __tablename__ = "strategies"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="PAUSED")
    allocation_pct: Mapped[float] = mapped_column(Float, default=0.0)
    win_rate: Mapped[float] = mapped_column(Float, default=0.0)
    profit_factor: Mapped[float] = mapped_column(Float, default=0.0)
    total_trades: Mapped[int] = mapped_column(Integer, default=0)
    total_profit: Mapped[float] = mapped_column(Float, default=0.0)
    config: Mapped[dict] = mapped_column(JSON, default={})

    # Relationships
    trades: Mapped[List["Trade"]] = relationship(
        "Trade",
        back_populates="strategy",
        cascade="all, delete-orphan",
        foreign_keys="Trade.strategy_id"
    )
    allocations: Mapped[List["CapitalAllocation"]] = relationship(
        "CapitalAllocation",
        back_populates="strategy",
        cascade="all, delete-orphan",
        foreign_keys="CapitalAllocation.strategy_id"
    )
