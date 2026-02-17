from uuid import uuid4
from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, Integer, Boolean, JSON, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class MLModel(Base, TimestampMixin):
    """Machine learning model registry."""

    __tablename__ = "ml_models"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_type: Mapped[str] = mapped_column(String(50), nullable=False)
    purpose: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")

    # Relationships
    versions: Mapped[List["ModelVersion"]] = relationship(
        "ModelVersion",
        back_populates="model",
        cascade="all, delete-orphan",
        foreign_keys="ModelVersion.model_id"
    )


class ModelVersion(Base, TimestampMixin):
    """Model version tracking with metrics."""

    __tablename__ = "model_versions"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4
    )
    model_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ml_models.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    metrics: Mapped[dict] = mapped_column(JSON, default={})
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    trained_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    samples_used: Mapped[int] = mapped_column(Integer, default=0)

    # Indexes
    __table_args__ = (
        Index("ix_model_versions_model_active", "model_id", "is_active"),
    )

    # Relationships
    model: Mapped["MLModel"] = relationship(
        "MLModel",
        back_populates="versions",
        foreign_keys=[model_id]
    )
