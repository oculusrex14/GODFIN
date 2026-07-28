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


def _setting(db: Session, key: str, default: str) -> AppSetting:
    item = db.query(AppSetting).filter_by(key=key).first()
    if item is None:
        item = AppSetting(key=key, value=default)
        db.add(item)
        db.flush()
    return item


def _status(db: Session) -> dict:
    completed = _setting(db, "onboarding_completed", "true").value == "true"
    step = int(_setting(db, "onboarding_step", "1").value or 1)
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
        "step": step,
        "transaction_count": transaction_count,
        "reviewed_count": max(0, transaction_count - review_count),
        "target_review_count": min(10, transaction_count),
    }


class OnboardingUpdate(BaseModel):
    step: int | None = Field(default=None, ge=1, le=5)
    completed: bool | None = None


@router.get("")
def onboarding_status(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    status = _status(db)
    db.commit()
    return status


@router.put("")
def update_onboarding(
    body: OnboardingUpdate,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    if body.step is not None:
        _setting(db, "onboarding_step", "1").value = str(body.step)
    if body.completed is not None:
        _setting(db, "onboarding_completed", "true").value = (
            "true" if body.completed else "false"
        )
    db.commit()
    return _status(db)
