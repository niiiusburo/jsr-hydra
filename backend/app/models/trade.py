from uuid import uuid4
from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, Float, Integer, Boolean, Text, DateTime, ForeignKey, func, BigInteger, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Trade(Base, TimestampMixin):
    """Individual trade record."""

    __tablename__ = "trades"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4
    )
    master_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("master_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    strategy_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("strategies.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    idempotency_key: Mapped[Optional[str]] = mapped_column(
        String(64),
        unique=True,
        nullable=True,
        index=True
    )
    mt5_ticket: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        unique=True,
        nullable=True,
        index=True
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    direction: Mapped[Optional[str]] = mapped_column(String(4), nullable=True)
    lots: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    entry_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    exit_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    stop_loss: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    take_profit: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    profit: Mapped[float] = mapped_column(Float, default=0.0)
    commission: Mapped[float] = mapped_column(Float, default=0.0)
    swap: Mapped[float] = mapped_column(Float, default=0.0)
    net_profit: Mapped[float] = mapped_column(Float, default=0.0)
    regime_at_entry: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    opened_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=func.now(),
        nullable=False
    )
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Indexes
    __table_args__ = (
        Index("ix_trades_master_status", "master_id", "status"),
        Index("ix_trades_strategy_opened", "strategy_id", "opened_at"),
    )

    # Relationships
    master_account: Mapped["MasterAccount"] = relationship(
        "MasterAccount",
        back_populates="trades",
        foreign_keys=[master_id]
    )
    strategy: Mapped["Strategy"] = relationship(
        "Strategy",
        back_populates="trades",
        foreign_keys=[strategy_id]
    )
