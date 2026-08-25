from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.time import utcnow_naive


class BehaviorInsightPreference(Base):
    __tablename__ = "behavior_insight_preferences"

    metric_key: Mapped[str] = mapped_column(String(50), primary_key=True)
    hidden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    correction_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        default=utcnow_naive, onupdate=utcnow_naive
    )
