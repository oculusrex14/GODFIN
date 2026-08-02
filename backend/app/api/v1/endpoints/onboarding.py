from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.app_setting import AppSetting
from app.models.transaction import Transaction

router = APIRouter()
CURRENT_TUTORIAL_VERSION = 1
SETUP_STEP_COUNT = 6
TUTORIAL_STEP_COUNT = 10


def _get_or_create_setting(db: Session, key: str, default: str) -> AppSetting:
    item = db.query(AppSetting).filter_by(key=key).first()
    if item is None:
        item = AppSetting(key=key, value=default)
        db.add(item)
        db.flush()
    return item


def _setting_value(db: Session, key: str, default: str) -> str:
    item = db.query(AppSetting).filter_by(key=key).first()
    return item.value if item is not None else default


def _bounded_setting_int(
    db: Session,
    key: str,
    default: int,
    maximum: int,
) -> int:
    try:
        value = int(_setting_value(db, key, str(default)))
    except (TypeError, ValueError):
        value = default
    return min(maximum, max(1, value))


def _status(db: Session) -> dict:
    completed = _setting_value(db, "onboarding_completed", "true") == "true"
    deferred = _setting_value(db, "onboarding_deferred", "false") == "true"
    step = _bounded_setting_int(db, "onboarding_step", 1, SETUP_STEP_COUNT)
    tutorial_step = _bounded_setting_int(
        db,
        "tutorial_step",
        1,
        TUTORIAL_STEP_COUNT,
    )
    try:
        tutorial_completed_version = max(
            0,
            int(_setting_value(db, "tutorial_completed_version", "0")),
        )
    except (TypeError, ValueError):
        tutorial_completed_version = 0
    transaction_count = (
        db.query(func.count(Transaction.id))
        .filter(Transaction.status != "deleted")
        .scalar()
        or 0
    )
    review_count = (
        db.query(func.count(Transaction.id))
        .filter(
            Transaction.status != "deleted",
            Transaction.category.is_(None),
        )
        .scalar()
        or 0
    )
    return {
        "completed": completed,
        "deferred": deferred,
        "step": step,
        "step_count": SETUP_STEP_COUNT,
        "tutorial_version": CURRENT_TUTORIAL_VERSION,
        "tutorial_step": tutorial_step,
        "tutorial_step_count": TUTORIAL_STEP_COUNT,
        "tutorial_completed": tutorial_completed_version >= CURRENT_TUTORIAL_VERSION,
        "tutorial_completed_version": tutorial_completed_version,
        "tutorial_update_available": (
            0 < tutorial_completed_version < CURRENT_TUTORIAL_VERSION
        ),
        "transaction_count": transaction_count,
        "reviewed_count": max(0, transaction_count - review_count),
        "target_review_count": min(10, transaction_count),
    }


class OnboardingUpdate(BaseModel):
    step: int | None = Field(default=None, ge=1, le=SETUP_STEP_COUNT)
    completed: bool | None = None
    deferred: bool | None = None
    tutorial_step: int | None = Field(
        default=None,
        ge=1,
        le=TUTORIAL_STEP_COUNT,
    )
    tutorial_completed: bool | None = None
    restart_tutorial: bool = False


@router.get("")
def onboarding_status(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    return _status(db)


@router.put("")
def update_onboarding(
    body: OnboardingUpdate,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    if body.step is not None:
        _get_or_create_setting(db, "onboarding_step", "1").value = str(body.step)
    if body.completed is not None:
        _get_or_create_setting(db, "onboarding_completed", "true").value = (
            "true" if body.completed else "false"
        )
    if body.deferred is not None:
        _get_or_create_setting(db, "onboarding_deferred", "false").value = (
            "true" if body.deferred else "false"
        )
    if body.tutorial_step is not None:
        _get_or_create_setting(db, "tutorial_step", "1").value = str(
            body.tutorial_step
        )
    if body.tutorial_completed is not None:
        _get_or_create_setting(db, "tutorial_completed_version", "0").value = (
            str(CURRENT_TUTORIAL_VERSION) if body.tutorial_completed else "0"
        )
    if body.restart_tutorial:
        _get_or_create_setting(db, "tutorial_step", "1").value = "1"
        _get_or_create_setting(db, "tutorial_completed_version", "0").value = "0"
    db.commit()
    return _status(db)
