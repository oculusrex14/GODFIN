from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, Float, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.time import utcnow_naive


class MerchantMemory(Base):
    __tablename__ = "merchant_memory"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    raw_string: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    subcategory: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    embedding_vector: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    embedding_model_version: Mapped[str] = mapped_column(String(50), default="all-MiniLM-L6-v2")
    avg_confidence: Mapped[float] = mapped_column(Float, default=1.0)
    times_seen: Mapped[int] = mapped_column(Integer, default=1)
    is_person: Mapped[bool] = mapped_column(Boolean, default=False)
    last_updated: Mapped[datetime] = mapped_column(default=utcnow_naive, onupdate=utcnow_naive)
