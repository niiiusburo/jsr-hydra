from uuid import uuid4
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Float, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class CapitalAllocation(Base, TimestampMixin):
    """Capital allocation across strategies and regimes."""

    __tablename__ = "capital_allocs"

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
    strategy_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("strategies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    regime_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("regime_states.id", ondelete="SET NULL"),
        nullable=True
    )
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    allocated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=func.now(),
        nullable=False
    )

    # Relationships
    master_account: Mapped["MasterAccount"] = relationship(
        "MasterAccount",
        back_populates="allocations",
        foreign_keys=[master_id]
    )
    strategy: Mapped["Strategy"] = relationship(
        "Strategy",
        back_populates="allocations",
        foreign_keys=[strategy_id]
    )
