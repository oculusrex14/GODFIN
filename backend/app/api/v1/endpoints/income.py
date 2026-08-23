"""Income sources management endpoints."""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.income_matching import (
    eligible_income_credit,
    scan_historical_income_matches,
    suggestion_evidence,
)
from app.core.time import utcnow_naive
from app.core.transaction_semantics import (
    TransactionSemantic,
    apply_transaction_semantic,
    verified_income_clause,
)
from app.models.account import Account
from app.models.audit_log import AuditLog
from app.models.income_source import IncomeMatchSuggestion, IncomeSource
from app.models.transaction import Transaction
from app.schemas.financial import (
    IncomeFrequency,
    PositiveMoney,
    YearMonth,
    reject_explicit_nulls,
)

router = APIRouter()


class IncomeSourceCreate(BaseModel):
    source_name: str = Field(min_length=1, max_length=100)
    expected_amount: Optional[PositiveMoney] = None
    frequency: IncomeFrequency = "monthly"
    next_expected_date: Optional[date] = None
    enforce_current_month: bool = False  # If true, apply to current month income
    is_active: bool = True
    effective_from: date = Field(default_factory=date.today)
    effective_to: Optional[date] = None
    amount_tolerance: float = Field(default=0.20, ge=0, le=1)
    confirmed_merchant_alias: Optional[str] = Field(default=None, max_length=255)
    account_id: Optional[str] = Field(default=None, min_length=1, max_length=36)
    payment_rail: Optional[str] = Field(default=None, min_length=1, max_length=32)

    @field_validator("source_name")
    @classmethod
    def normalize_source_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Income source name is required")
        return normalized

    @model_validator(mode="after")
    def validate_effective_period(self):
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("End date must be on or after the start date")
        return self


class IncomeSourceUpdate(BaseModel):
    source_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    expected_amount: Optional[PositiveMoney] = None
    frequency: Optional[IncomeFrequency] = None
    next_expected_date: Optional[date] = None
    enforce_current_month: Optional[bool] = None
    is_active: Optional[bool] = None
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None
    amount_tolerance: Optional[float] = Field(default=None, ge=0, le=1)
    confirmed_merchant_alias: Optional[str] = Field(default=None, max_length=255)
    account_id: Optional[str] = Field(default=None, min_length=1, max_length=36)
    payment_rail: Optional[str] = Field(default=None, min_length=1, max_length=32)

    @model_validator(mode="after")
    def reject_null_required_fields(self):
        return reject_explicit_nulls(
            self,
            {"source_name", "frequency", "enforce_current_month", "is_active"},
        )


class IncomeSourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_name: str
    expected_amount: Optional[float]
    frequency: str
    next_expected_date: Optional[str]
    enforce_current_month: bool
    last_detected_date: Optional[str]
    last_detected_amount: Optional[float]
    is_active: bool
    created_at: str
    effective_from: str
    effective_to: Optional[str]
    amount_tolerance: float
    confirmed_merchant_alias: Optional[str]
    account_id: Optional[str]
    payment_rail: Optional[str]

class IncomeSourceListResponse(BaseModel):
    items: List[IncomeSourceResponse]
    total: int


class IncomeStatsResponse(BaseModel):
    total_expected_monthly: float
    total_detected_this_month: float
    sources_count: int
    active_sources_count: int
    by_frequency: dict


class IncomeCoverageResponse(BaseModel):
    earliest_transaction_date: Optional[str]
    latest_transaction_date: Optional[str]


class IncomeMatchScanResponse(BaseModel):
    scanned: int
    candidates: int
    strong: int
    uncertain: int
    excluded_unsafe: int
    coverage_start: Optional[str]
    coverage_end: Optional[str]


class IncomeMatchSuggestionResponse(BaseModel):
    id: str
    transaction_id: str
    date: str
    amount: float
    merchant: str
    instrument: str
    account_id: str
    current_category: Optional[str]
    current_subcategory: Optional[str]
    current_semantic: str
    confidence: float
    strength: Literal["strong", "uncertain"]
    evidence: list[str]
    status: str


class IncomeMatchListResponse(BaseModel):
    items: list[IncomeMatchSuggestionResponse]
    total: int
    pending: int
    strong: int
    uncertain: int


class IncomeMatchDecision(BaseModel):
    suggestion_ids: list[str] = Field(min_length=1, max_length=200)

    @field_validator("suggestion_ids")
    @classmethod
    def unique_suggestion_ids(cls, values: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(item.strip() for item in values if item.strip()))
        if not normalized:
            raise ValueError("Select at least one suggested credit")
        return normalized


class IncomeMatchConfirm(IncomeMatchDecision):
    subcategory: Literal["Salary", "Freelance", "Interest", "Other Income"] = (
        "Other Income"
    )


class IncomeMatchDecisionResponse(BaseModel):
    updated: int
    source_id: str


def _calculate_default_next_date(frequency: str) -> Optional[date]:
    """Calculate default next expected date based on frequency."""
    today = date.today()
    if frequency == "monthly":
        if today.month == 12:
            return date(today.year + 1, 1, 1)
        else:
            return date(today.year, today.month + 1, 1)
    elif frequency == "quarterly":
        current_quarter = (today.month - 1) // 3
        next_quarter_month = (current_quarter + 1) * 3 + 1
        if next_quarter_month > 12:
            return date(today.year + 1, 1, 1)
        else:
            return date(today.year, next_quarter_month, 1)
    elif frequency == "annual":
        return date(today.year + 1, 1, 1)
    return None


def _source_to_response(source: IncomeSource) -> IncomeSourceResponse:
    """Convert IncomeSource model to response."""
    return IncomeSourceResponse(
        id=source.id,
        source_name=source.source_name,
        expected_amount=source.expected_amount,
        frequency=source.frequency,
        next_expected_date=source.next_expected_date.isoformat() if source.next_expected_date else None,
        enforce_current_month=source.enforce_current_month or False,
        last_detected_date=source.last_detected_date.isoformat() if source.last_detected_date else None,
        last_detected_amount=source.last_detected_amount,
        is_active=source.is_active,
        created_at=source.created_at.isoformat() if isinstance(source.created_at, datetime) else str(source.created_at),
        effective_from=source.effective_from.isoformat(),
        effective_to=source.effective_to.isoformat() if source.effective_to else None,
        amount_tolerance=float(source.amount_tolerance or 0),
        confirmed_merchant_alias=source.confirmed_merchant_alias,
        account_id=source.account_id,
        payment_rail=source.payment_rail,
    )


def _validated_account_id(db: Session, account_id: str | None) -> str | None:
    if not account_id:
        return None
    account = db.query(Account).filter_by(id=account_id, is_active=True).first()
    if not account:
        raise HTTPException(status_code=400, detail="Select an active account")
    return account.id


def _clean_optional(value: str | None) -> str | None:
    normalized = " ".join(str(value or "").split())
    return normalized or None


def _source_applies_to_month(
    source: IncomeSource,
    start_date: date,
    end_date: date,
) -> bool:
    if source.effective_from >= end_date:
        return False
    if source.effective_to is not None and source.effective_to < start_date:
        return False
    if not source.is_active and source.effective_to is None:
        return False
    month_offset = (
        (start_date.year - source.effective_from.year) * 12
        + start_date.month
        - source.effective_from.month
    )
    if source.frequency == "monthly":
        return True
    if source.frequency == "quarterly":
        return month_offset >= 0 and month_offset % 3 == 0
    if source.frequency == "annual":
        return month_offset >= 0 and month_offset % 12 == 0
    expected_date = source.next_expected_date or source.effective_from
    return start_date <= expected_date < end_date


@router.get("", response_model=IncomeSourceListResponse)
def list_income_sources(
    is_active: Optional[bool] = None,
    frequency: Optional[IncomeFrequency] = None,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """List all income sources."""
    query = db.query(IncomeSource)

    if is_active is not None:
        query = query.filter(IncomeSource.is_active == is_active)
    if frequency:
        query = query.filter(IncomeSource.frequency == frequency)

    items = query.order_by(IncomeSource.created_at.desc()).all()

    return IncomeSourceListResponse(
        items=[_source_to_response(item) for item in items],
        total=len(items),
    )


@router.post("", response_model=IncomeSourceResponse, status_code=201)
def create_income_source(
    body: IncomeSourceCreate,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Create a new income source."""
    next_expected_date = body.next_expected_date
    if next_expected_date is None and body.frequency in ["monthly", "quarterly", "annual"] and body.expected_amount:
        next_expected_date = _calculate_default_next_date(body.frequency)

    source = IncomeSource(
        id=str(uuid.uuid4()),
        source_name=body.source_name,
        expected_amount=body.expected_amount,
        frequency=body.frequency,
        next_expected_date=next_expected_date,
        enforce_current_month=body.enforce_current_month,
        is_active=body.is_active,
        effective_from=body.effective_from,
        effective_to=body.effective_to,
        amount_tolerance=body.amount_tolerance,
        confirmed_merchant_alias=_clean_optional(body.confirmed_merchant_alias),
        account_id=_validated_account_id(db, body.account_id),
        payment_rail=_clean_optional(body.payment_rail),
    )

    db.add(source)
    db.commit()
    db.refresh(source)

    return _source_to_response(source)


@router.get("/stats", response_model=IncomeStatsResponse)
def get_income_stats(
    month: Optional[YearMonth] = None,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Get income statistics for a given month."""
    if not month:
        month = date.today().strftime("%Y-%m")

    sources = db.query(IncomeSource).all()

    year, month_num = map(int, month.split("-"))
    start_date = date(year, month_num, 1)
    if month_num == 12:
        end_date = date(year + 1, 1, 1)
    else:
        end_date = date(year, month_num + 1, 1)

    total_expected_monthly = 0
    by_frequency = {"monthly": 0, "quarterly": 0, "annual": 0, "one_time": 0}

    for source in sources:
        if not _source_applies_to_month(source, start_date, end_date):
            continue

        expected = source.expected_amount or 0
        by_frequency.setdefault(source.frequency, 0)
        by_frequency[source.frequency] += expected
        total_expected_monthly += expected

    total_detected = (
        db.query(func.sum(Transaction.amount))
        .filter(
            verified_income_clause(Transaction),
            Transaction.date >= start_date,
            Transaction.date < end_date,
            Transaction.status != "deleted",
        )
        .scalar() or 0
    )

    return IncomeStatsResponse(
        total_expected_monthly=float(total_expected_monthly),
        total_detected_this_month=float(total_detected),
        sources_count=len(sources),
        active_sources_count=sum(1 for s in sources if s.is_active),
        by_frequency=by_frequency,
    )


@router.get("/coverage", response_model=IncomeCoverageResponse)
def get_income_coverage(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    earliest, latest = db.query(
        func.min(Transaction.date),
        func.max(Transaction.date),
    ).filter(Transaction.status != "deleted").one()
    return IncomeCoverageResponse(
        earliest_transaction_date=earliest.isoformat() if earliest else None,
        latest_transaction_date=latest.isoformat() if latest else None,
    )


@router.post("/{source_id}/matches/scan", response_model=IncomeMatchScanResponse)
def scan_income_source_matches(
    source_id: str,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    source = db.query(IncomeSource).filter_by(id=source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Income source not found")
    result = scan_historical_income_matches(db, source)
    db.commit()
    return IncomeMatchScanResponse(
        scanned=result.scanned,
        candidates=result.candidates,
        strong=result.strong,
        uncertain=result.uncertain,
        excluded_unsafe=result.excluded_unsafe,
        coverage_start=result.coverage_start.isoformat() if result.coverage_start else None,
        coverage_end=result.coverage_end.isoformat() if result.coverage_end else None,
    )


@router.get("/{source_id}/matches", response_model=IncomeMatchListResponse)
def list_income_source_matches(
    source_id: str,
    status: Literal["pending", "confirmed", "dismissed", "stale"] = "pending",
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    if not db.query(IncomeSource.id).filter_by(id=source_id).first():
        raise HTTPException(status_code=404, detail="Income source not found")
    rows = (
        db.query(IncomeMatchSuggestion, Transaction)
        .join(Transaction, Transaction.id == IncomeMatchSuggestion.transaction_id)
        .filter(
            IncomeMatchSuggestion.income_source_id == source_id,
            IncomeMatchSuggestion.status == status,
        )
        .order_by(
            IncomeMatchSuggestion.confidence.desc(),
            Transaction.date.desc(),
        )
        .all()
    )
    items = [
        IncomeMatchSuggestionResponse(
            id=suggestion.id,
            transaction_id=transaction.id,
            date=transaction.date.isoformat(),
            amount=float(transaction.amount),
            merchant=(
                transaction.merchant_normalized
                or transaction.merchant_raw
                or transaction.raw_text[:120]
            ),
            instrument=transaction.instrument,
            account_id=transaction.account_id,
            current_category=transaction.category,
            current_subcategory=transaction.subcategory,
            current_semantic=transaction.semantic_type,
            confidence=suggestion.confidence,
            strength=suggestion.strength,
            evidence=suggestion_evidence(suggestion),
            status=suggestion.status,
        )
        for suggestion, transaction in rows
    ]
    return IncomeMatchListResponse(
        items=items,
        total=len(items),
        pending=len(items) if status == "pending" else 0,
        strong=sum(item.strength == "strong" for item in items),
        uncertain=sum(item.strength == "uncertain" for item in items),
    )


def _decision_suggestions(
    db: Session,
    source_id: str,
    suggestion_ids: list[str],
) -> tuple[IncomeSource, list[tuple[IncomeMatchSuggestion, Transaction]]]:
    source = db.query(IncomeSource).filter_by(id=source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Income source not found")
    rows = (
        db.query(IncomeMatchSuggestion, Transaction)
        .join(Transaction, Transaction.id == IncomeMatchSuggestion.transaction_id)
        .filter(
            IncomeMatchSuggestion.income_source_id == source_id,
            IncomeMatchSuggestion.id.in_(suggestion_ids),
        )
        .all()
    )
    if len(rows) != len(suggestion_ids):
        raise HTTPException(status_code=404, detail="A selected income match was not found")
    return source, rows


@router.post(
    "/{source_id}/matches/confirm",
    response_model=IncomeMatchDecisionResponse,
)
def confirm_income_source_matches(
    source_id: str,
    body: IncomeMatchConfirm,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    source, rows = _decision_suggestions(db, source_id, body.suggestion_ids)
    pending_rows = [row for row in rows if row[0].status == "pending"]
    if any(row[0].status not in {"pending", "confirmed"} for row in rows):
        raise HTTPException(status_code=409, detail="Rescan before confirming this match")
    for _suggestion, transaction in pending_rows:
        if (
            not eligible_income_credit(transaction)
            or transaction.date < source.effective_from
            or (
                source.effective_to is not None
                and transaction.date > source.effective_to
            )
        ):
            raise HTTPException(
                status_code=409,
                detail="A selected credit is no longer safe to confirm as income",
            )

    now = utcnow_naive()
    for suggestion, transaction in pending_rows:
        old_value = json.dumps(
            {
                "category": transaction.category,
                "subcategory": transaction.subcategory,
                "semantic_type": transaction.semantic_type,
                "is_income": bool(transaction.is_income),
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        transaction.category = "INCOME"
        transaction.subcategory = body.subcategory
        transaction.classification_source = "user"
        transaction.confidence = 1.0
        apply_transaction_semantic(transaction, TransactionSemantic.INCOME.value)
        transaction.updated_at = now
        suggestion.status = "confirmed"
        suggestion.decided_at = now
        suggestion.updated_at = now
        db.add(
            AuditLog(
                transaction_id=transaction.id,
                field_changed="income_source_confirmation",
                old_value=old_value,
                new_value=json.dumps(
                    {
                        "income_source_id": source.id,
                        "category": "INCOME",
                        "subcategory": body.subcategory,
                        "semantic_type": TransactionSemantic.INCOME.value,
                        "is_income": True,
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                change_source="user_income_match",
            )
        )
        db.query(IncomeMatchSuggestion).filter(
            IncomeMatchSuggestion.transaction_id == transaction.id,
            IncomeMatchSuggestion.income_source_id != source.id,
            IncomeMatchSuggestion.status == "pending",
        ).update(
            {"status": "stale", "updated_at": now},
            synchronize_session=False,
        )
        if not source.confirmed_merchant_alias:
            source.confirmed_merchant_alias = _clean_optional(
                transaction.merchant_normalized or transaction.merchant_raw
            )

    confirmed_transactions = [transaction for _suggestion, transaction in rows]
    if confirmed_transactions:
        latest = max(confirmed_transactions, key=lambda item: (item.date, item.id))
        source.last_detected_date = latest.date
        source.last_detected_amount = latest.amount
    db.commit()
    return IncomeMatchDecisionResponse(updated=len(pending_rows), source_id=source.id)


@router.post(
    "/{source_id}/matches/dismiss",
    response_model=IncomeMatchDecisionResponse,
)
def dismiss_income_source_matches(
    source_id: str,
    body: IncomeMatchDecision,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    source, rows = _decision_suggestions(db, source_id, body.suggestion_ids)
    now = utcnow_naive()
    updated = 0
    for suggestion, _transaction in rows:
        if suggestion.status == "pending":
            suggestion.status = "dismissed"
            suggestion.decided_at = now
            suggestion.updated_at = now
            updated += 1
    db.commit()
    return IncomeMatchDecisionResponse(updated=updated, source_id=source.id)


@router.get("/{source_id}", response_model=IncomeSourceResponse)
def get_income_source(
    source_id: str,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Get a specific income source."""
    source = db.query(IncomeSource).filter_by(id=source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Income source not found")

    return _source_to_response(source)


@router.put("/{source_id}", response_model=IncomeSourceResponse)
def update_income_source(
    source_id: str,
    body: IncomeSourceUpdate,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Update an income source."""
    source = db.query(IncomeSource).filter_by(id=source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Income source not found")

    update_data = body.model_dump(exclude_unset=True)
    effective_from = update_data.get("effective_from", source.effective_from)
    effective_to = update_data.get("effective_to", source.effective_to)
    if effective_to is not None and effective_to < effective_from:
        raise HTTPException(
            status_code=422,
            detail="End date must be on or after the start date",
        )
    if "account_id" in update_data:
        update_data["account_id"] = _validated_account_id(
            db,
            update_data["account_id"],
        )
    for field in ("confirmed_merchant_alias", "payment_rail"):
        if field in update_data:
            update_data[field] = _clean_optional(update_data[field])

    for field, value in update_data.items():
        setattr(source, field, value)

    db.commit()
    db.refresh(source)

    return _source_to_response(source)


@router.delete("/{source_id}", status_code=204)
def delete_income_source(
    source_id: str,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Delete an income source."""
    source = db.query(IncomeSource).filter_by(id=source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Income source not found")

    db.delete(source)
    db.commit()
