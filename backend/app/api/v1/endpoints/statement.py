from __future__ import annotations

import asyncio
import hashlib
import logging
import secrets
import threading
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.v1.entitlements import conditional_entitlement, enforce_feature
from app.core.auth import get_current_user
from app.core.audit import FinalizedPeriodError
from app.core.classifier import classify_transaction
from app.core.database import get_db
from app.core.errors import LocalOperationError, StateConflictError
from app.core.merchant_memory_service import upsert_merchant_memory
from app.core.parsers import account_requirements, parse_registered_statement
from app.core.reconciliation import (
    ReconciliationService,
    import_new_transactions,
    reconcile_statement,
)
from app.core.statement_parser import ParsedStatement
from app.core.transaction_semantics import (
    TransactionSemantic,
    apply_category_semantic,
    ledger_credit_clause,
    ledger_debit_clause,
)
from app.models.account import Account
from app.models.income_source import IncomeSource
from app.models.transaction import Transaction
from app.schemas.statement import IncomeSourceCreate, IncomeSourceUpdate

logger = logging.getLogger(__name__)

router = APIRouter()


# --- Helpers ---

def _resolve_account_id(db: Session, statement_type: str, account_id: str = None) -> str:
    """Resolve account_id from statement type if not provided."""
    if account_id:
        acct = db.query(Account).filter_by(id=account_id, is_active=True).first()
        if not acct:
            raise HTTPException(status_code=400, detail="Invalid account_id")
        if acct.bank.upper() != "HDFC":
            enforce_feature(db, "multi_bank")
        return account_id

    bank, account_type = account_requirements(statement_type)
    query = db.query(Account).filter_by(is_active=True)
    if bank:
        query = query.filter(Account.bank == bank)
    if account_type:
        query = query.filter(Account.account_type == account_type)
    acct = query.order_by(Account.created_at.asc()).first()

    if not acct:
        raise HTTPException(status_code=400, detail="No matching account found. Please specify account_id.")
    if acct.bank.upper() != "HDFC":
        enforce_feature(db, "multi_bank")
    return acct.id


SUPPORTED_EXTENSIONS = ('.pdf', '.xls', '.xlsx')
MAX_STATEMENT_BYTES = 10 * 1024 * 1024
STATEMENT_READ_CHUNK_BYTES = 1024 * 1024
_PARSER_SLOTS = threading.BoundedSemaphore(value=2)


def _detect_file_format(filename: str, contents: bytes) -> str:
    """Detect file format from magic bytes, falling back to extension."""
    if contents[:5].startswith(b'%PDF-'):
        return 'pdf'
    if contents[:4] == b'\xd0\xcf\x11\xe0':  # OLE2 compound document (.xls)
        return 'xls'
    if contents[:2] == b'PK':  # ZIP-based (.xlsx)
        return 'xlsx'
    # Fallback to extension
    lower = filename.lower()
    if lower.endswith('.xls'):
        return 'xls'
    if lower.endswith('.xlsx'):
        return 'xlsx'
    if lower.endswith('.pdf'):
        return 'pdf'
    return 'unknown'


async def _read_and_parse(file: UploadFile, password: Optional[str]):
    """Read file and parse PDF or XLS, returning the parse result."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    lower_name = file.filename.lower()
    if not any(lower_name.endswith(ext) for ext in SUPPORTED_EXTENSIONS):
        raise HTTPException(status_code=400, detail="Supported formats: PDF, XLS, XLSX")

    contents_buffer = bytearray()
    while True:
        chunk = await file.read(STATEMENT_READ_CHUNK_BYTES)
        if not chunk:
            break
        contents_buffer.extend(chunk)
        if len(contents_buffer) > MAX_STATEMENT_BYTES:
            raise HTTPException(status_code=413, detail="File too large (max 10MB)")
    contents = bytes(contents_buffer)

    fmt = _detect_file_format(file.filename, contents)

    if fmt not in {"pdf", "xls", "xlsx"}:
        raise HTTPException(status_code=400, detail="Unrecognized file format")
    if not _PARSER_SLOTS.acquire(blocking=False):
        raise HTTPException(
            status_code=429,
            detail="Two statements are already being inspected. Try again shortly.",
            headers={"Retry-After": "3"},
        )
    try:
        parse_result = await asyncio.to_thread(
            parse_registered_statement,
            contents,
            fmt,
            password,
        )
    finally:
        _PARSER_SLOTS.release()
    parse_result.source_digest = hashlib.sha256(contents).hexdigest()

    if parse_result.errors:
        raise HTTPException(
            status_code=400,
            detail=f"Parse errors: {'; '.join(parse_result.errors)}",
        )

    if not parse_result.transactions:
        raise HTTPException(
            status_code=400,
            detail="No transactions found in statement",
        )

    if not parse_result.recognized or parse_result.reconciliation_status != "passed":
        raise HTTPException(
            status_code=400,
            detail="Statement type or financial controls could not be verified",
        )

    return parse_result


# --- Statement Upload (3-step flow) ---

@router.post("/ingest/upload/preview")
async def preview_statement(
    file: UploadFile = File(...),
    password: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Step 1: Parse PDF and return transaction preview. No database writes."""
    parse_result = await _read_and_parse(file, password)

    # Convert to ParsedStatement for consistent output
    parsed = ParsedStatement.from_statement_result(parse_result)

    return {
        "statement_type": parse_result.statement_type,
        "parser_profile": parse_result.parser_profile,
        "recognized": parse_result.recognized,
        "reconciliation_status": parse_result.reconciliation_status,
        "reconciliation_method": parse_result.reconciliation_method,
        "parse_fingerprint": parse_result.source_digest,
        "period_start": str(parse_result.period_start) if parse_result.period_start else None,
        "period_end": str(parse_result.period_end) if parse_result.period_end else None,
        "control_totals": {
            "opening_balance": parse_result.opening_balance,
            "closing_balance": parse_result.closing_balance,
            "total_debits": parse_result.total_debits,
            "total_credits": parse_result.total_credits,
        },
        "total_transactions": len(parsed.transactions),
        "transactions": [
            {
                "date": str(t.date),
                "description": t.description,
                "amount": t.amount,
                "type": t.type,
                "reference": t.reference,
                "instrument": t.instrument,
                "is_transfer": t.is_transfer,
                "is_income": t.is_income,
                "semantic_type": t.semantic_type,
                "merchant_name": t.merchant_name,
            }
            for t in parsed.transactions
        ],
    }


@router.post("/ingest/upload/reconcile")
@conditional_entitlement("multi_bank")
async def reconcile_statement_preview(
    file: UploadFile = File(...),
    password: Optional[str] = Form(None),
    account_id: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Step 2: Parse + reconcile against existing transactions. No imports."""
    parse_result = await _read_and_parse(file, password)
    parsed = ParsedStatement.from_statement_result(parse_result)

    resolved_account_id = _resolve_account_id(db, parse_result.statement_type, account_id)

    recon_result = ReconciliationService.reconcile(db, parsed, resolved_account_id)
    income_txns = ReconciliationService.detect_income_sources(db, parsed)

    # Balance reconciliation
    statement_closing_balance = None
    computed_balance = None
    balance_discrepancy = None

    # Get closing balance from the last transaction in sorted order
    sorted_txns = sorted(parsed.transactions, key=lambda t: t.date)
    if sorted_txns and sorted_txns[-1].balance is not None:
        statement_closing_balance = sorted_txns[-1].balance

        # Compute system balance for this account up to statement period end
        from sqlalchemy import func as sa_func

        period_end = parse_result.period_end
        if not period_end and sorted_txns:
            from datetime import timedelta
            period_end = sorted_txns[-1].date + timedelta(days=1)

        if period_end:
            bal_query = db.query(Transaction).filter(
                Transaction.account_id == resolved_account_id,
                Transaction.date < period_end,
                Transaction.status != 'deleted',
            )
            credit_sum = bal_query.filter(
                ledger_credit_clause(Transaction),
            ).with_entities(sa_func.coalesce(sa_func.sum(Transaction.amount), 0)).scalar()

            debit_sum = bal_query.filter(
                ledger_debit_clause(Transaction),
            ).with_entities(sa_func.coalesce(sa_func.sum(Transaction.amount), 0)).scalar()

            computed_balance = round(float(credit_sum) - float(debit_sum), 2)
            balance_discrepancy = round(statement_closing_balance - computed_balance, 2)

    return {
        "account_id": resolved_account_id,
        "statement_type": parse_result.statement_type,
        "parser_profile": parse_result.parser_profile,
        "reconciliation_status": parse_result.reconciliation_status,
        "reconciliation_method": parse_result.reconciliation_method,
        "parse_fingerprint": parse_result.source_digest,
        "control_totals": {
            "opening_balance": parse_result.opening_balance,
            "closing_balance": parse_result.closing_balance,
            "total_debits": parse_result.total_debits,
            "total_credits": parse_result.total_credits,
        },
        "total_parsed": recon_result.total_parsed,
        "matched_count": len(recon_result.duplicate_transactions),
        "possible_count": len(recon_result.potential_duplicates),
        "new_count": recon_result.total_new,
        "income_count": len(income_txns),
        "statement_closing_balance": statement_closing_balance,
        "computed_balance": computed_balance,
        "balance_discrepancy": balance_discrepancy,
        "new_transactions": [
            {
                "date": str(t.date),
                "description": t.description,
                "amount": t.amount,
                "type": t.type,
            }
            for t in recon_result.new_transactions
        ],
        "potential_duplicates": [
            {
                "parsed": {
                    "date": str(p.date),
                    "description": p.description,
                    "amount": p.amount,
                },
                "existing": {
                    "id": e.id,
                    "date": str(e.date),
                    "merchant": e.merchant_normalized or e.merchant_raw,
                    "amount": float(e.amount),
                },
            }
            for p, e in recon_result.potential_duplicates
        ],
        "income_detected": [
            {
                "date": str(t.date),
                "description": t.description,
                "amount": t.amount,
            }
            for t in income_txns
        ],
    }


@router.post("/ingest/upload/import")
@conditional_entitlement("multi_bank")
async def import_statement(
    file: UploadFile = File(...),
    password: Optional[str] = Form(None),
    account_id: Optional[str] = Form(None),
    import_new: bool = Form(True),
    detect_income: bool = Form(True),
    confirm_reconciled: bool = Form(False),
    accepted_fingerprint: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Step 3: Parse + reconcile + import new transactions with classification."""
    try:
        parse_result = await _read_and_parse(file, password)
        if not confirm_reconciled:
            raise HTTPException(
                status_code=400,
                detail="Review the reconciled preview and explicitly confirm before importing",
            )
        if (
            not accepted_fingerprint
            or len(accepted_fingerprint) != 64
            or not secrets.compare_digest(
                accepted_fingerprint.lower(),
                parse_result.source_digest,
            )
        ):
            raise HTTPException(
                status_code=409,
                detail="The selected file changed after review; preview it again before importing",
            )
        parsed = ParsedStatement.from_statement_result(parse_result)

        resolved_account_id = _resolve_account_id(db, parse_result.statement_type, account_id)

        recon_result = ReconciliationService.reconcile(db, parsed, resolved_account_id)

        imported_count = 0
        classified_count = 0
        review_queue_count = 0
        imported_txns = []

        if import_new and recon_result.new_transactions:
            imported_txns = import_new_transactions(
                db, recon_result.new_transactions, resolved_account_id
            )
            imported_count = len(imported_txns)

            # Classify each imported transaction and update merchant memory
            for i, txn in enumerate(imported_txns):
                # Get corresponding parsed transaction for narration hints
                parsed_txn = recon_result.new_transactions[i] if i < len(recon_result.new_transactions) else None

                try:
                    classification = classify_transaction(
                        db,
                        txn.merchant_normalized or txn.merchant_raw or '',
                        float(txn.amount),
                        txn.instrument or 'statement',
                        vpa_handle=txn.vpa_handle,
                    )
                    if classification.category:
                        txn.category = classification.category
                        txn.subcategory = classification.subcategory
                        txn.confidence = classification.confidence
                        txn.classification_source = classification.source
                        apply_category_semantic(
                            txn,
                            explicitly_classified=classification.source
                            in {"exact_match", "confirmed_pattern", "rule"},
                        )
                        classified_count += 1

                        # Update merchant memory for future classifications
                        upsert_merchant_memory(
                            db,
                            txn.merchant_normalized or txn.merchant_raw or '',
                            classification.category,
                            classification.subcategory,
                            classification.confidence,
                        )
                    elif parsed_txn and parsed_txn.category_hint:
                        # Classifier failed — use parser's narration-based hint as fallback
                        txn.category = parsed_txn.category_hint
                        txn.subcategory = getattr(parsed_txn, 'subcategory_hint', None)
                        txn.confidence = 0.65
                        txn.classification_source = 'narration_hint'
                        apply_category_semantic(
                            txn,
                            explicitly_classified=(
                                getattr(parsed_txn, 'semantic_type', None)
                                == TransactionSemantic.INCOME.value
                            ),
                        )
                        classified_count += 1
                    else:
                        review_queue_count += 1
                except Exception as e:
                    logger.warning(f"Classification failed for {txn.merchant_raw}: {e}")
                    review_queue_count += 1

            merchant_keys = {
                (txn.merchant_normalized, txn.account_id)
                for txn in imported_txns
                if txn.merchant_normalized
            }
            if merchant_keys:
                from app.core.goal_contributions import (
                    detect_goal_contribution_suggestions,
                )
                from app.core.license import has_feature
                from app.core.product_depth import sync_subscription_suggestions
                from app.core.recurring import detect_recurring_patterns

                detect_recurring_patterns(db, merchant_keys=merchant_keys)
                sync_subscription_suggestions(db, run_detection=False)
                if has_feature(db, "fd_rd_goal_detection"):
                    detect_goal_contribution_suggestions(
                        db, transactions=imported_txns
                    )

        # Detect income
        income_items = []
        if detect_income:
            income_txns = ReconciliationService.detect_income_sources(db, parsed)
            income_items = [
                {
                    "date": str(t.date),
                    "description": t.description,
                    "amount": t.amount,
                }
                for t in income_txns
            ]

        db.commit()

        # Balance reconciliation
        statement_closing_balance = None
        computed_balance = None
        balance_discrepancy = None

        sorted_txns = sorted(parsed.transactions, key=lambda t: t.date)
        if sorted_txns and sorted_txns[-1].balance is not None:
            statement_closing_balance = sorted_txns[-1].balance

            from sqlalchemy import func as sa_func

            period_end = parse_result.period_end
            if not period_end and sorted_txns:
                from datetime import timedelta
                period_end = sorted_txns[-1].date + timedelta(days=1)

            if period_end:
                bal_query = db.query(Transaction).filter(
                    Transaction.account_id == resolved_account_id,
                    Transaction.date < period_end,
                    Transaction.status != 'deleted',
                )
                credit_sum = bal_query.filter(
                    ledger_credit_clause(Transaction),
                ).with_entities(sa_func.coalesce(sa_func.sum(Transaction.amount), 0)).scalar()

                debit_sum = bal_query.filter(
                    ledger_debit_clause(Transaction),
                ).with_entities(sa_func.coalesce(sa_func.sum(Transaction.amount), 0)).scalar()

                computed_balance = round(float(credit_sum) - float(debit_sum), 2)
                balance_discrepancy = round(statement_closing_balance - computed_balance, 2)

        return {
            "statement_type": parse_result.statement_type,
            "total_parsed": recon_result.total_parsed,
            "matched": len(recon_result.duplicate_transactions),
            "skipped_dup": len(recon_result.duplicate_transactions),
            "possible": len(recon_result.potential_duplicates),
            "new_imported": imported_count,
            "imported": imported_count,
            "classified": classified_count,
            "review_queue": review_queue_count,
            "errors": [],
            "income_detected": len(income_items),
            "income_items": income_items,
            "statement_closing_balance": statement_closing_balance,
            "computed_balance": computed_balance,
            "balance_discrepancy": balance_discrepancy,
        }
    except FinalizedPeriodError as exc:
        db.rollback()
        raise StateConflictError(
            code="FINALIZED_PERIOD_READ_ONLY",
            message=(
                "This statement includes a finalized month that is read-only. "
                "Reopen the month before importing."
            ),
            hint="Reopen that month before importing these transactions.",
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise LocalOperationError(
            code="STATEMENT_IMPORT_FAILED",
            message="GODFIN could not complete this statement import.",
            hint="No partial import was kept. Review the file and try again.",
            status_code=503,
        ) from exc


@router.post("/ingest/upload")
async def upload_statement_legacy(
    file: UploadFile = File(...),
    password: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Retired because one-step imports bypass explicit reconciliation review."""
    raise HTTPException(
        status_code=410,
        detail="One-step import was retired. Use preview, reconcile, then confirmed import.",
    )


# --- Income Sources ---

@router.get("/income-sources")
def list_income_sources(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    sources = db.query(IncomeSource).filter_by(is_active=True).all()
    return [
        {
            "id": s.id,
            "source_name": s.source_name,
            "expected_amount": s.expected_amount,
            "frequency": s.frequency,
            "last_detected_date": str(s.last_detected_date) if s.last_detected_date else None,
            "last_detected_amount": s.last_detected_amount,
            "is_active": s.is_active,
        }
        for s in sources
    ]


@router.post("/income-sources", status_code=201)
def create_income_source(
    body: IncomeSourceCreate,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    source = IncomeSource(
        source_name=body.source_name,
        expected_amount=body.expected_amount,
        frequency=body.frequency,
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return {
        "id": source.id,
        "source_name": source.source_name,
        "expected_amount": source.expected_amount,
        "frequency": source.frequency,
    }


@router.put("/income-sources/{source_id}")
def update_income_source(
    source_id: str,
    body: IncomeSourceUpdate,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    source = db.query(IncomeSource).filter_by(id=source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Income source not found")

    if body.source_name is not None:
        source.source_name = body.source_name
    if body.expected_amount is not None:
        source.expected_amount = body.expected_amount
    if body.frequency is not None:
        source.frequency = body.frequency
    if body.is_active is not None:
        source.is_active = body.is_active

    db.commit()
    return {"id": source.id, "source_name": source.source_name, "status": "updated"}


@router.delete("/income-sources/{source_id}", status_code=204)
def delete_income_source(
    source_id: str,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    source = db.query(IncomeSource).filter_by(id=source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Income source not found")

    source.is_active = False
    db.commit()
