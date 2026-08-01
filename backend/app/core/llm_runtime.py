"""Runtime activation for encrypted LLM configurations."""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.core.encryption import decrypt
from app.core.llm_providers import create_provider
from app.core.llm_privacy import has_hosted_data_consent, is_local_provider
from app.core.llm_service import StubLLMProvider, set_llm_provider
from app.models.llm_config import LLMConfiguration

logger = logging.getLogger(__name__)


def provider_from_config(config: LLMConfiguration):
    """Construct a provider using plaintext only in process memory."""
    provider = create_provider(
        provider=config.provider,
        model=config.model,
        api_key=decrypt(config.api_key) if config.api_key else None,
        base_url=config.base_url,
    )
    provider.is_local = is_local_provider(config.provider)
    provider.hosted_data_consent = has_hosted_data_consent(config)
    return provider


def activate_configuration(config: LLMConfiguration):
    if not has_hosted_data_consent(config):
        raise ValueError(
            "Review and accept the hosted AI data disclosure before activation"
        )
    provider = provider_from_config(config)
    set_llm_provider(provider)
    return provider


def initialize_active_llm(db: Session) -> Optional[LLMConfiguration]:
    config = db.query(LLMConfiguration).filter_by(is_active=True).first()
    if config is None:
        logger.info("No active LLM configuration found, using stub provider")
        return None
    try:
        activate_configuration(config)
    except ValueError:
        set_llm_provider(StubLLMProvider())
        logger.warning(
            "Hosted LLM configuration requires renewed data consent before use"
        )
        return config
    logger.info("LLM provider initialized: %s with model %s", config.provider, config.model)
    return config
