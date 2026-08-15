"""LLM Configuration API endpoints."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.errors import IntegrationUnavailableError, InvalidOperationError
from app.core.encryption import encrypt, decrypt
from app.core.llm_providers import create_provider, get_available_providers
from app.core.llm_privacy import (
    HOSTED_DATA_CONSENT_VERSION,
    has_hosted_data_consent,
    is_local_provider,
    record_hosted_data_consent,
)
from app.core.llm_runtime import activate_configuration
from app.core.llm_service import set_llm_provider
from app.api.v1.entitlements import require_entitlement
from app.models.llm_config import LLMConfiguration

logger = logging.getLogger(__name__)

router = APIRouter()
AI_CLASSIFICATION_ENTITLEMENT = require_entitlement("ai_classification")


# ============================================================================
# Schemas
# ============================================================================

class LLMConfigCreate(BaseModel):
    provider: str = Field(
        ...,
        min_length=1,
        max_length=50,
        pattern=r"^[a-z0-9_-]+$",
        description="Provider type",
    )
    auth_method: str = Field(
        default="openapi",
        min_length=1,
        max_length=50,
        pattern=r"^[a-z0-9_-]+$",
        description="Authentication method",
    )
    model: str = Field(..., min_length=1, max_length=200, description="Model identifier")
    api_key: Optional[str] = Field(
        None,
        min_length=1,
        max_length=8192,
        description="API key for OpenAPI auth",
    )
    base_url: Optional[str] = Field(
        None,
        min_length=1,
        max_length=2048,
        description="Custom base URL",
    )
    hosted_data_consent: bool = False


class LLMConfigUpdate(BaseModel):
    model: Optional[str] = Field(default=None, min_length=1, max_length=200)
    api_key: Optional[str] = Field(default=None, min_length=1, max_length=8192)
    base_url: Optional[str] = Field(default=None, min_length=1, max_length=2048)
    is_active: Optional[bool] = None
    hosted_data_consent: Optional[bool] = None


class LLMConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    provider: str
    auth_method: str
    model: str
    base_url: Optional[str]
    is_active: bool
    has_api_key: bool
    is_local: bool
    hosted_data_consent: bool
    consent_version: str
    created_at: str
    updated_at: str

class TestConnectionRequest(BaseModel):
    provider: str = Field(min_length=1, max_length=50, pattern=r"^[a-z0-9_-]+$")
    model: str = Field(min_length=1, max_length=200)
    api_key: Optional[str] = Field(default=None, min_length=1, max_length=8192)
    base_url: Optional[str] = Field(default=None, min_length=1, max_length=2048)


class TestConnectionResponse(BaseModel):
    success: bool
    message: str


class LLMProviderResponse(BaseModel):
    name: str
    is_local: bool
    auth_methods: list[str]
    requires_auth: bool
    models: dict[str, object] | list[str]
    description: str


class LLMActionResponse(BaseModel):
    success: bool
    message: str


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/providers", response_model=dict[str, LLMProviderResponse])
def list_providers(_user: bool = Depends(get_current_user)):
    """List all available LLM providers with their supported models."""
    return get_available_providers()


@router.get("/config", response_model=Optional[LLMConfigResponse])
def get_llm_config(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Get the current active LLM configuration."""
    config = db.query(LLMConfiguration).filter_by(is_active=True).first()
    if not config:
        return None

    return {
        "id": config.id,
        "provider": config.provider,
        "auth_method": config.auth_method,
        "model": config.model,
        "base_url": config.base_url,
        "is_active": config.is_active,
        "has_api_key": bool(config.api_key),
        "is_local": is_local_provider(config.provider),
        "hosted_data_consent": has_hosted_data_consent(config),
        "consent_version": HOSTED_DATA_CONSENT_VERSION,
        "created_at": config.created_at.isoformat() if config.created_at else None,
        "updated_at": config.updated_at.isoformat() if config.updated_at else None,
    }


@router.post(
    "/config",
    response_model=LLMConfigResponse,
    dependencies=[Depends(AI_CLASSIFICATION_ENTITLEMENT)],
)
def create_llm_config(
    request: LLMConfigCreate,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Create a new LLM configuration."""
    if request.provider not in get_available_providers():
        raise HTTPException(status_code=422, detail="Unknown AI provider")
    if not is_local_provider(request.provider) and not request.hosted_data_consent:
        raise HTTPException(
            status_code=400,
            detail="Accept the hosted AI data disclosure before saving this provider",
        )
    # Deactivate any existing config
    db.query(LLMConfiguration).filter_by(is_active=True).update({"is_active": False})

    # Encrypt API key before storing
    encrypted_api_key = encrypt(request.api_key) if request.api_key else None

    # Create new config
    config = LLMConfiguration(
        provider=request.provider,
        auth_method=request.auth_method,
        model=request.model,
        api_key=encrypted_api_key,
        base_url=request.base_url,
        is_active=True,
    )
    if not is_local_provider(request.provider):
        record_hosted_data_consent(config, True)
    db.add(config)

    # Activate before commit so a broken configuration cannot replace the
    # currently working provider while appearing active.
    try:
        db.flush()
        activate_configuration(config)
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=422,
            detail="The AI configuration could not be activated",
        ) from exc
    db.commit()
    db.refresh(config)
    logger.info("Activated LLM provider: %s with model %s", config.provider, config.model)

    return {
        "id": config.id,
        "provider": config.provider,
        "auth_method": config.auth_method,
        "model": config.model,
        "base_url": config.base_url,
        "is_active": config.is_active,
        "has_api_key": bool(config.api_key),
        "is_local": is_local_provider(config.provider),
        "hosted_data_consent": has_hosted_data_consent(config),
        "consent_version": HOSTED_DATA_CONSENT_VERSION,
        "created_at": config.created_at.isoformat(),
        "updated_at": config.updated_at.isoformat(),
    }


@router.put(
    "/config/{config_id}",
    response_model=LLMConfigResponse,
    dependencies=[Depends(AI_CLASSIFICATION_ENTITLEMENT)],
)
def update_llm_config(
    config_id: str,
    request: LLMConfigUpdate,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Update an existing LLM configuration."""
    config = db.query(LLMConfiguration).filter_by(id=config_id).first()
    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")

    if request.model is not None:
        config.model = request.model
    if request.api_key is not None:
        config.api_key = encrypt(request.api_key)
    if request.base_url is not None:
        config.base_url = request.base_url
    if request.is_active is not None:
        config.is_active = request.is_active

        # If activating, deactivate others
        if request.is_active:
            db.query(LLMConfiguration).filter(
                LLMConfiguration.id != config_id,
                LLMConfiguration.is_active == True
            ).update({"is_active": False})

    if request.hosted_data_consent is not None and not is_local_provider(
        config.provider
    ):
        record_hosted_data_consent(config, request.hosted_data_consent)
    if config.is_active and not has_hosted_data_consent(config):
        raise HTTPException(
            status_code=400,
            detail="Accept the hosted AI data disclosure before activation",
        )

    # Reactivate before commit so invalid changes roll back atomically.
    if config.is_active:
        try:
            db.flush()
            activate_configuration(config)
        except Exception as exc:
            db.rollback()
            raise HTTPException(
                status_code=422,
                detail="The AI configuration could not be activated",
            ) from exc
    db.commit()
    db.refresh(config)

    return {
        "id": config.id,
        "provider": config.provider,
        "auth_method": config.auth_method,
        "model": config.model,
        "base_url": config.base_url,
        "is_active": config.is_active,
        "has_api_key": bool(config.api_key),
        "is_local": is_local_provider(config.provider),
        "hosted_data_consent": has_hosted_data_consent(config),
        "consent_version": HOSTED_DATA_CONSENT_VERSION,
        "created_at": config.created_at.isoformat(),
        "updated_at": config.updated_at.isoformat(),
    }


@router.delete("/config/{config_id}", response_model=LLMActionResponse)
def delete_llm_config(
    config_id: str,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Delete an LLM configuration."""
    config = db.query(LLMConfiguration).filter_by(id=config_id).first()
    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")

    was_active = config.is_active
    db.delete(config)
    db.commit()

    # If we deleted the active config, fall back to stub
    if was_active:
        from app.core.llm_service import StubLLMProvider
        set_llm_provider(StubLLMProvider())
        logger.info("Deactivated LLM provider, using stub")

    return {"success": True, "message": "Configuration deleted"}


@router.post(
    "/config/test",
    response_model=TestConnectionResponse,
    dependencies=[Depends(AI_CLASSIFICATION_ENTITLEMENT)],
)
def test_llm_connection(
    request: TestConnectionRequest,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Test connection to an LLM provider without saving."""
    try:
        provider = create_provider(
            provider=request.provider,
            model=request.model,
            api_key=request.api_key,
            base_url=request.base_url,
        )
        success, _provider_message = provider.test_connection()
        if not success:
            raise IntegrationUnavailableError(
                code="LLM_CONNECTION_FAILED",
                message="GODFIN could not connect to that AI provider.",
                hint="Check the provider, model, address, and key, then try again.",
            )
        return {"success": True, "message": "Connection successful"}
    except ValueError as exc:
        raise InvalidOperationError(
            code="LLM_CONFIGURATION_INVALID",
            message="The AI connection settings are not valid.",
            hint="Check the provider, model, address, and key.",
        ) from exc
    except IntegrationUnavailableError:
        raise
    except Exception as exc:
        raise IntegrationUnavailableError(
            code="LLM_CONNECTION_FAILED",
            message="GODFIN could not connect to that AI provider.",
            hint="Check the provider, model, address, and key, then try again.",
        ) from exc


@router.post(
    "/config/activate/{config_id}",
    dependencies=[Depends(AI_CLASSIFICATION_ENTITLEMENT)],
    response_model=LLMActionResponse,
)
def activate_llm_config(
    config_id: str,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Activate a specific LLM configuration."""
    config = db.query(LLMConfiguration).filter_by(id=config_id).first()
    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")

    # Deactivate all others
    db.query(LLMConfiguration).filter(
        LLMConfiguration.id != config_id,
        LLMConfiguration.is_active == True
    ).update({"is_active": False})

    config.is_active = True
    if not has_hosted_data_consent(config):
        raise HTTPException(
            status_code=409,
            detail="Accept the hosted AI data disclosure before activation",
        )
    # Activate provider
    try:
        activate_configuration(config)
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=422,
            detail="The AI configuration could not be activated",
        ) from exc
    db.commit()
    logger.info("Activated LLM provider: %s", config.provider)
    return {"success": True, "message": "Configuration activated"}
