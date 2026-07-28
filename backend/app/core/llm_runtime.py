"""Runtime activation for encrypted LLM configurations."""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.core.encryption import decrypt
from app.core.llm_providers import create_provider
from app.core.llm_service import set_llm_provider
from app.models.llm_config import LLMConfiguration

logger = logging.getLogger(__name__)


def provider_from_config(config: LLMConfiguration):
    """Construct a provider using plaintext only in process memory."""
    return create_provider(
        provider=config.provider,
        model=config.model,
        api_key=decrypt(config.api_key) if config.api_key else None,
        base_url=config.base_url,
    )


def activate_configuration(config: LLMConfiguration):
    provider = provider_from_config(config)
    set_llm_provider(provider)
    return provider


def initialize_active_llm(db: Session) -> Optional[LLMConfiguration]:
    config = db.query(LLMConfiguration).filter_by(is_active=True).first()
    if config is None:
        logger.info("No active LLM configuration found, using stub provider")
        return None
    activate_configuration(config)
    logger.info("LLM provider initialized: %s with model %s", config.provider, config.model)
    return config
