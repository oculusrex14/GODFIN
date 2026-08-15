from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.v1.entitlements import require_entitlement
from app.core.audit import FinalizedPeriodError
from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.errors import StateConflictError
from app.core.product_depth import (
    decide_transfer_match,
    list_transfer_matches,
    scan_transfer_candidates,
)
from app.models.transfer_match import TransferMatch

router = APIRouter()
MULTI_BANK_ENTITLEMENT = require_entitlement("multi_bank")


class TransferDecision(BaseModel):
    decision: str = Field(pattern=r"^(confirm|ignore|snooze)$")
    snooze_days: int = Field(default=7, ge=1, le=90)
    note: str | None = Field(default=None, max_length=255)


class TransferTransactionResponse(BaseModel):
    id: str
    date: str
    merchant: str
    amount: float
    type: str
    account: str


class TransferMatchResponse(BaseModel):
    id: str
    amount: float
    date_gap_days: int
    confidence: float
    status: str
    snoozed_until: str | None
    decision_note: str | None
    debit: TransferTransactionResponse
    credit: TransferTransactionResponse


class TransferScanResponse(BaseModel):
    created: int
    candidates: list[TransferMatchResponse]


class TransferDecisionResponse(BaseModel):
    id: str
    status: str


@router.get(
    "",
    dependencies=[Depends(MULTI_BANK_ENTITLEMENT)],
    response_model=list[TransferMatchResponse],
)
def get_transfer_matches(
    include_resolved: bool = False,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    return list_transfer_matches(db, include_resolved=include_resolved)


@router.post(
    "/scan",
    dependencies=[Depends(MULTI_BANK_ENTITLEMENT)],
    response_model=TransferScanResponse,
)
def scan_transfers(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    created = scan_transfer_candidates(db)
    db.commit()
    return {"created": created, "candidates": list_transfer_matches(db)}


@router.post(
    "/{match_id}/decision",
    dependencies=[Depends(MULTI_BANK_ENTITLEMENT)],
    response_model=TransferDecisionResponse,
)
def update_transfer_match(
    match_id: str,
    body: TransferDecision,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
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
        raise StateConflictError(
            code="FINALIZED_PERIOD_READ_ONLY",
            message=(
                "One of these transactions belongs to a finalized month. "
                "Reopen the affected month before changing this match."
            ),
            hint="Reopen the affected month before changing this match.",
        ) from exc
    db.commit()
    return {"id": match.id, "status": match.status}
