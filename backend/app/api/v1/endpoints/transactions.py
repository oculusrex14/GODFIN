from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.transaction import Transaction
from app.schemas.transaction import (
    TransactionCreate,
    TransactionListResponse,
    TransactionResponse,
    TransactionUpdate,
)

router = APIRouter()


@router.post("", response_model=TransactionResponse, status_code=201)
def create_transaction(
    body: TransactionCreate,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    txn = Transaction(
        id=str(uuid.uuid4()),
        date=body.date,
        time=body.time,
        raw_text=f"Manual: {body.merchant_raw} {body.amount}",
        merchant_raw=body.merchant_raw,
        merchant_normalized=body.merchant_raw.upper().strip(),
        amount=body.amount,
        type=body.type,
        instrument=body.instrument,
        account_id=body.account_id,
        category=body.category,
        subcategory=body.subcategory,
        confidence=1.0 if body.category else None,
        classification_source="user" if body.category else None,
        source="manual",
        is_income=body.category == "INCOME" if body.category else False,
        is_transfer=body.category == "TRANSFERS" if body.category else False,
        notes=body.notes,
        tags=body.tags,
    )
    db.add(txn)
    db.commit()
    db.refresh(txn)
    return txn


@router.get("", response_model=TransactionListResponse)
def list_transactions(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    category: Optional[str] = None,
    subcategory: Optional[str] = None,
    account_id: Optional[str] = None,
    search: Optional[str] = None,
    type: Optional[str] = None,
    sort_by: str = Query("date", pattern=r"^(date|amount)$"),
    sort_order: str = Query("desc", pattern=r"^(asc|desc)$"),
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    query = db.query(Transaction).filter(Transaction.status != "deleted")

    if date_from:
        query = query.filter(Transaction.date >= date_from)
    if date_to:
        query = query.filter(Transaction.date <= date_to)
    if category:
        query = query.filter(Transaction.category == category)
    if subcategory:
        query = query.filter(Transaction.subcategory == subcategory)
    if account_id:
        query = query.filter(Transaction.account_id == account_id)
    if type:
        query = query.filter(Transaction.type == type)
    if search:
        pattern = f"%{search}%"
        query = query.filter(
            or_(
                Transaction.merchant_raw.ilike(pattern),
                Transaction.merchant_normalized.ilike(pattern),
                Transaction.notes.ilike(pattern),
            )
        )

    total = query.count()

    sort_col = Transaction.date if sort_by == "date" else Transaction.amount
    if sort_order == "desc":
        query = query.order_by(sort_col.desc(), Transaction.created_at.desc())
    else:
        query = query.order_by(sort_col.asc(), Transaction.created_at.asc())

    items = query.offset((page - 1) * page_size).limit(page_size).all()

    return TransactionListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{transaction_id}", response_model=TransactionResponse)
def get_transaction(
    transaction_id: str,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    txn = db.query(Transaction).filter_by(id=transaction_id).first()
    if not txn or txn.status == "deleted":
        raise HTTPException(status_code=404, detail="Transaction not found")
    return txn


@router.put("/{transaction_id}", response_model=TransactionResponse)
def update_transaction(
    transaction_id: str,
    body: TransactionUpdate,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    txn = db.query(Transaction).filter_by(id=transaction_id).first()
    if not txn or txn.status == "deleted":
        raise HTTPException(status_code=404, detail="Transaction not found")

    if txn.is_locked:
        raise HTTPException(
            status_code=403,
            detail="Transaction is locked (month finalized). Reopen audit to edit.",
        )

    try:
        update_data = body.model_dump(exclude_unset=True)

        # Track changes for audit logging
        from app.models.audit_log import AuditLog
        for field, new_value in update_data.items():
            old_value = getattr(txn, field, None)
            if old_value != new_value:
                db.add(AuditLog(
                    transaction_id=txn.id,
                    field_changed=field,
                    old_value=str(old_value) if old_value is not None else None,
                    new_value=str(new_value) if new_value is not None else None,
                    change_source="user_update",
                ))

        if "category" in update_data and update_data["category"] is not None:
            txn.classification_source = "user"
            txn.confidence = 1.0
            txn.is_income = update_data["category"] == "INCOME"
            txn.is_transfer = update_data["category"] == "TRANSFERS"

        for field, value in update_data.items():
            setattr(txn, field, value)

        txn.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(txn)
        return txn
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update transaction: {str(e)}")


@router.delete("/{transaction_id}", status_code=204)
def delete_transaction(
    transaction_id: str,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    txn = db.query(Transaction).filter_by(id=transaction_id).first()
    if not txn or txn.status == "deleted":
        raise HTTPException(status_code=404, detail="Transaction not found")

    if txn.is_locked:
        raise HTTPException(
            status_code=403,
            detail="Transaction is locked (month finalized). Reopen audit to edit.",
        )

    # Soft delete the transaction
    txn.status = "deleted"
    txn.updated_at = datetime.now(timezone.utc)

    # Cascade soft delete to related TransactionSplits
    from app.models.transaction_split import TransactionSplit
    splits = db.query(TransactionSplit).filter(
        TransactionSplit.parent_transaction_id == transaction_id
    ).all()
    for split in splits:
        split.status = "deleted"

    # Create audit log entry for the deletion
    from app.models.audit_log import AuditLog
    db.add(AuditLog(
        transaction_id=txn.id,
        field_changed="status",
        old_value=txn.status,
        new_value="deleted",
        change_source="user_delete",
    ))

    db.commit()
