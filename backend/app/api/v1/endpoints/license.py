from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.license import (
    LicenseError,
    activate_license,
    deactivate_license,
    license_status,
    require_feature,
    reverify_license,
)

router = APIRouter()


class LicenseActivation(BaseModel):
    license_key: str = Field(min_length=20, max_length=120)


def _raise_license_error(exc: LicenseError):
    raise HTTPException(
        status_code=exc.status_code,
        detail={
            "code": exc.code,
            "message": str(exc),
            "hint": "Open godfin.dev/account if you need the key resent.",
            "retriable": exc.retriable,
        },
    ) from exc


def enforce_feature(db: Session, feature: str) -> None:
    try:
        require_feature(db, feature)
    except LicenseError as exc:
        _raise_license_error(exc)


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
        _raise_license_error(exc)


@router.post("/verify")
def verify(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    try:
        return reverify_license(db)
    except LicenseError as exc:
        _raise_license_error(exc)


@router.delete("")
def deactivate(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    return deactivate_license(db)
