from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.api.v1.entitlements import raise_license_error
from app.core.license import (
    LicenseError,
    activate_license,
    deactivate_license,
    license_status,
    reverify_license,
)
from app.core.entitlements import entitlement_manifest

router = APIRouter()


class LicenseActivation(BaseModel):
    license_key: str = Field(min_length=20, max_length=120)


class LicenseStatusResponse(BaseModel):
    tier: str
    licensed_tier: str | None
    status: str
    valid: bool
    features: list[str]
    verified_at: str | None
    offline_grace_until: str | None
    entitlement_integrity: str | None
    monthly_credits: int
    hosted_credits_included: int
    topup_credits: int
    masked_key: str | None
    message: str
    website_url: str


class NavigationEntitlement(BaseModel):
    feature: str
    required_tier: str
    label: str
    explanation: str


class LicenseNavigationResponse(BaseModel):
    tier: str
    features: list[str]
    routes: dict[str, NavigationEntitlement]


@router.get("", response_model=LicenseStatusResponse)
def get_license_status(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    return license_status(db)


@router.get("/navigation", response_model=LicenseNavigationResponse)
def get_license_navigation(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Return presentation metadata without changing authoritative gates."""
    status = license_status(db)
    routes = entitlement_manifest().get("navigation", {})
    return {
        "tier": status["tier"],
        "features": status["features"],
        "routes": routes,
    }


@router.post("/activate", response_model=LicenseStatusResponse)
def activate(
    body: LicenseActivation,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    try:
        return activate_license(db, body.license_key)
    except LicenseError as exc:
        raise_license_error(exc)


@router.post("/verify", response_model=LicenseStatusResponse)
def verify(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    try:
        return reverify_license(db)
    except LicenseError as exc:
        raise_license_error(exc)


@router.delete("", response_model=LicenseStatusResponse)
def deactivate(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    return deactivate_license(db)
