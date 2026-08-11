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

router = APIRouter()


class LicenseActivation(BaseModel):
    license_key: str = Field(min_length=20, max_length=120)


@router.get("")
def get_license_status(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    return license_status(db)


@router.post("/activate")
def activate(
    body: LicenseActivation,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    try:
        return activate_license(db, body.license_key)
    except LicenseError as exc:
        raise_license_error(exc)


@router.post("/verify")
def verify(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    try:
        return reverify_license(db)
    except LicenseError as exc:
        raise_license_error(exc)


@router.delete("")
def deactivate(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    return deactivate_license(db)
