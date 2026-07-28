"""LLM Configuration model for storing provider settings."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.time import utcnow_naive


class LLMConfiguration(Base):
    """Stores LLM provider configuration and API credentials."""

    __tablename__ = "llm_configurations"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    # Provider selection
    provider: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Provider type: ollama_cloud, ollama_local, anthropic, openai, gemini, moonshot, zai, deepseek, qwen, minimax"
    )

    # Authentication method
    auth_method: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="openapi",
        comment="oauth, openapi, or none"
    )

    # Model selection
    model: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Model identifier (e.g., gpt-4o, claude-opus-4-6)"
    )

    # API credentials (encrypted storage)
    api_key: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Encrypted API key for OpenAPI authentication"
    )

    # OAuth tokens (if using OAuth)
    oauth_token: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Encrypted OAuth access token"
    )

    oauth_refresh_token: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Encrypted OAuth refresh token"
    )

    oauth_token_expires: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="OAuth token expiration time"
    )

    # Custom base URL (for Ollama, etc.)
    base_url: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="Custom base URL for the API (e.g., http://localhost:11434 for local Ollama)"
    )

    # Status
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False
    )

    # Metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        nullable=False
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False
    )

    # Additional provider-specific settings (stored as JSON string)
    settings_json: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Additional provider-specific settings as JSON"
    )

    def to_dict(self, include_sensitive: bool = False) -> dict:
        """Convert to dictionary. Optionally include sensitive fields."""
        result = {
            "id": self.id,
            "provider": self.provider,
            "auth_method": self.auth_method,
            "model": self.model,
            "base_url": self.base_url,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

        if include_sensitive:
            result["api_key"] = self.api_key
            result["oauth_token"] = self.oauth_token
            result["oauth_refresh_token"] = self.oauth_refresh_token
            result["oauth_token_expires"] = self.oauth_token_expires.isoformat() if self.oauth_token_expires else None
        else:
            # Mask sensitive data
            result["has_api_key"] = bool(self.api_key)
            result["has_oauth_token"] = bool(self.oauth_token)

        return result
