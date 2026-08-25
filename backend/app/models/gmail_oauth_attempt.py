from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.time import utcnow_naive


class GmailOAuthAttempt(Base):
    """Short-lived, one-time state for the installed-app Gmail OAuth flow.

    The provider state is stored only as a SHA-256 digest. The PKCE verifier is
    encrypted with GODFIN's stable local encryption key. Attempts are bound to
    the hashed desktop session that initiated them, but the callback can safely
    validate the random state without receiving the bearer token.
    """

    __tablename__ = "gmail_oauth_attempts"
    __table_args__ = (
        Index("ix_gmail_oauth_attempts_expires_at", "expires_at"),
        Index("ix_gmail_oauth_attempts_session", "session_token_hash"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    state_hash: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    session_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    code_verifier_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    redirect_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow_naive
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    consumed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
