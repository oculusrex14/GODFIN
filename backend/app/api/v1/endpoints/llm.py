"""LLM Configuration API endpoints."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.encryption import encrypt, decrypt
from app.core.llm_providers import create_provider, get_available_providers
from app.core.llm_runtime import activate_configuration
from app.core.llm_service import set_llm_provider
from app.api.v1.endpoints.license import enforce_feature
from app.models.llm_config import LLMConfiguration

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# Schemas
# ============================================================================

class LLMConfigCreate(BaseModel):
    provider: str = Field(..., description="Provider type")
    auth_method: str = Field(default="openapi", description="Authentication method")
    model: str = Field(..., description="Model identifier")
    api_key: Optional[str] = Field(None, description="API key for OpenAPI auth")
    base_url: Optional[str] = Field(None, description="Custom base URL")


class LLMConfigUpdate(BaseModel):
    model: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    is_active: Optional[bool] = None


class LLMConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    provider: str
    auth_method: str
    model: str
    base_url: Optional[str]
    is_active: bool
    has_api_key: bool
    created_at: str
    updated_at: str

class TestConnectionRequest(BaseModel):
    provider: str
    model: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None


class TestConnectionResponse(BaseModel):
    success: bool
    message: str


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/providers")
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
        "created_at": config.created_at.isoformat() if config.created_at else None,
        "updated_at": config.updated_at.isoformat() if config.updated_at else None,
    }


@router.post("/config", response_model=LLMConfigResponse)
def create_llm_config(
    request: LLMConfigCreate,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Create a new LLM configuration."""
    enforce_feature(db, "ai_classification")
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
    db.add(config)
    db.commit()
    db.refresh(config)

    # Activate the provider (decrypt key for API use)
    try:
        activate_configuration(config)
        logger.info(f"Activated LLM provider: {config.provider} with model {config.model}")
    except Exception as e:
        logger.warning(f"Failed to activate provider: {e}")

    return {
        "id": config.id,
        "provider": config.provider,
        "auth_method": config.auth_method,
        "model": config.model,
        "base_url": config.base_url,
        "is_active": config.is_active,
        "has_api_key": bool(config.api_key),
        "created_at": config.created_at.isoformat(),
        "updated_at": config.updated_at.isoformat(),
    }


@router.put("/config/{config_id}", response_model=LLMConfigResponse)
def update_llm_config(
    config_id: str,
    request: LLMConfigUpdate,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Update an existing LLM configuration."""
    enforce_feature(db, "ai_classification")
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

    db.commit()
    db.refresh(config)

    # Reactivate provider if config changed
    if config.is_active:
        try:
            activate_configuration(config)
        except Exception as e:
            logger.warning(f"Failed to reactivate provider: {e}")

    return {
        "id": config.id,
        "provider": config.provider,
        "auth_method": config.auth_method,
        "model": config.model,
        "base_url": config.base_url,
        "is_active": config.is_active,
        "has_api_key": bool(config.api_key),
        "created_at": config.created_at.isoformat(),
        "updated_at": config.updated_at.isoformat(),
    }


@router.delete("/config/{config_id}")
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


@router.post("/config/test", response_model=TestConnectionResponse)
def test_llm_connection(
    request: TestConnectionRequest,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Test connection to an LLM provider without saving."""
    enforce_feature(db, "ai_classification")
    try:
        provider = create_provider(
            provider=request.provider,
            model=request.model,
            api_key=request.api_key,
            base_url=request.base_url,
        )
        success, message = provider.test_connection()
        return {"success": success, "message": message}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        return {"success": False, "message": f"Connection test failed: {str(e)}"}


@router.post("/config/activate/{config_id}")
def activate_llm_config(
    config_id: str,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Activate a specific LLM configuration."""
    enforce_feature(db, "ai_classification")
    config = db.query(LLMConfiguration).filter_by(id=config_id).first()
    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")

    # Deactivate all others
    db.query(LLMConfiguration).filter(
        LLMConfiguration.id != config_id,
        LLMConfiguration.is_active == True
    ).update({"is_active": False})

    config.is_active = True
    db.commit()

    # Activate provider
    try:
        activate_configuration(config)
        logger.info(f"Activated LLM provider: {config.provider}")
        return {"success": True, "message": "Configuration activated"}
    except Exception as e:
        logger.error(f"Failed to activate provider: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to activate: {str(e)}")
