from uuid import uuid4
from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, Float, Integer, ForeignKey, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class MasterAccount(Base, TimestampMixin):
    """Master trading account that generates trade signals."""

    __tablename__ = "master_accounts"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4
    )
    mt5_login: Mapped[int] = mapped_column(
        Integer,
        unique=True,
        nullable=False,
        index=True
    )
    broker: Mapped[str] = mapped_column(String(100), nullable=True)
    balance: Mapped[float] = mapped_column(Float, default=0.0)
    equity: Mapped[float] = mapped_column(Float, default=0.0)
    peak_equity: Mapped[float] = mapped_column(Float, default=0.0)
    daily_start_balance: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(20), default="RUNNING")

    # Relationships
    trades: Mapped[List["Trade"]] = relationship(
        "Trade",
        back_populates="master_account",
        cascade="all, delete-orphan",
        foreign_keys="Trade.master_id"
    )
    follower_accounts: Mapped[List["FollowerAccount"]] = relationship(
        "FollowerAccount",
        back_populates="master_account",
        cascade="all, delete-orphan",
        foreign_keys="FollowerAccount.master_id"
    )
    allocations: Mapped[List["CapitalAllocation"]] = relationship(
        "CapitalAllocation",
        back_populates="master_account",
        cascade="all, delete-orphan",
        foreign_keys="CapitalAllocation.master_id"
    )


class FollowerAccount(Base, TimestampMixin):
    """Follower account that copies trades from a master account."""

    __tablename__ = "follower_accounts"

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
    mt5_login: Mapped[int] = mapped_column(
        Integer,
        unique=True,
        nullable=False,
        index=True
    )
    broker: Mapped[str] = mapped_column(String(100), nullable=True)
    lot_multiplier: Mapped[float] = mapped_column(Float, default=1.0)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")

    # Relationships
    master_account: Mapped["MasterAccount"] = relationship(
        "MasterAccount",
        back_populates="follower_accounts",
        foreign_keys=[master_id]
    )


class EquitySnapshot(Base):
    """Periodic equity snapshot for charting the equity curve.

    Recorded by the engine every ~5 minutes with current account
    balance, equity, and margin usage.  The table is capped at
    MAX_SNAPSHOTS_PER_ACCOUNT rows per master account to prevent
    unbounded growth.
    """

    __tablename__ = "equity_snapshots"

    MAX_SNAPSHOTS_PER_ACCOUNT = 1000

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    master_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("master_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), nullable=False, index=True
    )
    equity: Mapped[float] = mapped_column(Float, nullable=False)
    balance: Mapped[float] = mapped_column(Float, nullable=False)
    margin_used: Mapped[float] = mapped_column(Float, default=0.0)
