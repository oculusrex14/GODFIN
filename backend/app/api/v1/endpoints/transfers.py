from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.v1.endpoints.license import enforce_feature
from app.core.audit import FinalizedPeriodError
from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.product_depth import (
    decide_transfer_match,
    list_transfer_matches,
    scan_transfer_candidates,
)
from app.models.transfer_match import TransferMatch

router = APIRouter()


class TransferDecision(BaseModel):
    decision: str = Field(pattern=r"^(confirm|ignore|snooze)$")
    snooze_days: int = Field(default=7, ge=1, le=90)
    note: str | None = Field(default=None, max_length=255)


@router.get("")
def get_transfer_matches(
    include_resolved: bool = False,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    enforce_feature(db, "multi_bank")
    return list_transfer_matches(db, include_resolved=include_resolved)


@router.post("/scan")
def scan_transfers(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    enforce_feature(db, "multi_bank")
    created = scan_transfer_candidates(db)
    db.commit()
    return {"created": created, "candidates": list_transfer_matches(db)}


@router.post("/{match_id}/decision")
def update_transfer_match(
    match_id: str,
    body: TransferDecision,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    enforce_feature(db, "multi_bank")
    match = db.query(TransferMatch).filter_by(id=match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="Transfer match not found")
    try:
        decide_transfer_match(
            db,
            match,
            body.decision,
            snooze_days=body.snooze_days,
            note=body.note,
        )
    except FinalizedPeriodError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return {"id": match.id, "status": match.status}
