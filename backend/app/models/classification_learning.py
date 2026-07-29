from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.time import utcnow_naive


class ClassificationPattern(Base):
    __tablename__ = "classification_patterns"
    __table_args__ = (
        Index("ix_classification_patterns_active", "is_active"),
        Index("ix_classification_patterns_category", "category"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    pattern_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    pattern_display: Mapped[str] = mapped_column(String(255), nullable=False)
    instrument: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    subcategory: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    confirmations: Mapped[int] = mapped_column(Integer, default=1)
    confidence: Mapped[float] = mapped_column(Float, default=0.75)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
    )


class ClassificationCorrection(Base):
    __tablename__ = "classification_corrections"
    __table_args__ = (
        Index("ix_classification_corrections_pattern", "pattern_key"),
        Index("ix_classification_corrections_created", "created_at"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    transaction_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("transactions.id"),
        nullable=False,
    )
    merchant_normalized: Mapped[str] = mapped_column(String(255), nullable=False)
    pattern_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    instrument: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    old_category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    old_subcategory: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    new_category: Mapped[str] = mapped_column(String(50), nullable=False)
    new_subcategory: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    undone_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
