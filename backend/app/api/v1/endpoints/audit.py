from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.audit import (
    discard_audit,
    finalize_audit,
    get_month_status,
    reopen_audit,
    start_audit,
)
from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.errors import InvalidOperationError, LocalOperationError
from app.models.audit_session import AuditSession

router = APIRouter()


class AuditStartRequest(BaseModel):
    year: int = Field(..., ge=2020, le=2099)
    month: int = Field(..., ge=1, le=12)


def _session_to_dict(s: AuditSession) -> dict:
    return {
        'id': s.id,
        'period_year': s.period_year,
        'period_month': s.period_month,
        'status': s.status,
        'change_summary': s.change_summary,
        'created_at': s.created_at.isoformat() if s.created_at else None,
        'finalized_at': s.finalized_at.isoformat() if s.finalized_at else None,
    }


@router.post("/start", status_code=201)
def audit_start(
    body: AuditStartRequest,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    try:
        session = start_audit(db, body.year, body.month)
        db.commit()
        return _session_to_dict(session)
    except ValueError as exc:
        raise InvalidOperationError(
            code="AUDIT_START_INVALID",
            message="This month cannot be opened for review in its current state.",
            hint="Check the month status and try again.",
        ) from exc


@router.get("/sessions")
def list_sessions(
    year: int = None,
    month: int = None,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    query = db.query(AuditSession)
    if year is not None:
        query = query.filter_by(period_year=year)
    if month is not None:
        query = query.filter_by(period_month=month)
    sessions = query.order_by(AuditSession.created_at.desc()).all()
    return [_session_to_dict(s) for s in sessions]


@router.get("/sessions/{session_id}")
def get_session(
    session_id: str,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    session = db.query(AuditSession).filter_by(id=session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return _session_to_dict(session)


@router.post("/{session_id}/finalize")
def audit_finalize(
    session_id: str,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    try:
        session = finalize_audit(db, session_id)
        db.commit()
        return _session_to_dict(session)
    except ValueError as exc:
        db.rollback()
        raise InvalidOperationError(
            code="AUDIT_FINALIZE_INVALID",
            message="This review cannot be finalized in its current state.",
            hint="Finish or resolve the outstanding review items first.",
        ) from exc
    except Exception as exc:
        db.rollback()
        raise LocalOperationError(
            code="AUDIT_FINALIZE_FAILED",
            message="GODFIN could not finalize this review.",
            hint="Your existing data is unchanged. Try again.",
        ) from exc


@router.post("/{session_id}/discard")
def audit_discard(
    session_id: str,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    try:
        session = discard_audit(db, session_id)
        db.commit()
        return _session_to_dict(session)
    except ValueError as exc:
        db.rollback()
        raise InvalidOperationError(
            code="AUDIT_DISCARD_INVALID",
            message="This review cannot be discarded in its current state.",
        ) from exc
    except Exception as exc:
        db.rollback()
        raise LocalOperationError(
            code="AUDIT_DISCARD_FAILED",
            message="GODFIN could not discard this review.",
            hint="Your existing data is unchanged. Try again.",
        ) from exc


@router.post("/{session_id}/reopen")
def audit_reopen(
    session_id: str,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    try:
        new_session = reopen_audit(db, session_id)
        db.commit()
        return _session_to_dict(new_session)
    except ValueError as exc:
        db.rollback()
        raise InvalidOperationError(
            code="AUDIT_REOPEN_INVALID",
            message="This month cannot be reopened in its current state.",
        ) from exc
    except Exception as exc:
        db.rollback()
        raise LocalOperationError(
            code="AUDIT_REOPEN_FAILED",
            message="GODFIN could not reopen this month.",
            hint="Your finalized data is unchanged. Try again.",
        ) from exc


@router.get("/month-status")
def month_status(
    year: int,
    month: int,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    status = get_month_status(db, year, month)
    return {'year': year, 'month': month, 'status': status}
