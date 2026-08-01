from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import CheckConstraint, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.time import utcnow_naive


class AuditSession(Base):
    __tablename__ = "audit_sessions"

    # Valid status values for audit state machine
    VALID_STATUSES = ("draft", "finalized", "locked", "discarded")

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    period_year: Mapped[int] = mapped_column(Integer, nullable=False)
    period_month: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="draft",
    )
    change_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow_naive)
    finalized_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    # Database-level constraint for valid status values
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'finalized', 'locked', 'discarded')",
            name="valid_audit_status",
        ),
        Index(
            "uq_audit_sessions_active_period",
            "period_year",
            "period_month",
            unique=True,
            sqlite_where=text(
                "status IN ('draft', 'finalized', 'locked')"
            ),
        ),
    )
