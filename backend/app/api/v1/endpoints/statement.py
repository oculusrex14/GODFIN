from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.classifier import classify_transaction
from app.core.database import get_db
from app.core.merchant_memory_service import upsert_merchant_memory
from app.core.parsers import account_requirements, parse_registered_statement
from app.core.reconciliation import (
    ReconciliationService,
    import_new_transactions,
    reconcile_statement,
)
from app.core.statement_parser import ParsedStatement
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
            from app.api.v1.endpoints.license import enforce_feature

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
        from app.api.v1.endpoints.license import enforce_feature

        enforce_feature(db, "multi_bank")
    return acct.id


SUPPORTED_EXTENSIONS = ('.pdf', '.xls', '.xlsx')


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

    contents = await file.read()

    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")

    fmt = _detect_file_format(file.filename, contents)

    if fmt not in {"pdf", "xls", "xlsx"}:
        raise HTTPException(status_code=400, detail="Unrecognized file format")
    parse_result = parse_registered_statement(contents, fmt, password=password)

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
        "period_start": str(parse_result.period_start) if parse_result.period_start else None,
        "period_end": str(parse_result.period_end) if parse_result.period_end else None,
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
                "merchant_name": t.merchant_name,
            }
            for t in parsed.transactions
        ],
    }


@router.post("/ingest/upload/reconcile")
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
                (Transaction.is_income == True) | (Transaction.type == 'credit'),
            ).with_entities(sa_func.coalesce(sa_func.sum(Transaction.amount), 0)).scalar()

            debit_sum = bal_query.filter(
                Transaction.type == 'debit',
            ).with_entities(sa_func.coalesce(sa_func.sum(Transaction.amount), 0)).scalar()

            computed_balance = round(float(credit_sum) - float(debit_sum), 2)
            balance_discrepancy = round(statement_closing_balance - computed_balance, 2)

    return {
        "account_id": resolved_account_id,
        "statement_type": parse_result.statement_type,
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
async def import_statement(
    file: UploadFile = File(...),
    password: Optional[str] = Form(None),
    account_id: Optional[str] = Form(None),
    import_new: bool = Form(True),
    detect_income: bool = Form(True),
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Step 3: Parse + reconcile + import new transactions with classification."""
    try:
        parse_result = await _read_and_parse(file, password)
        parsed = ParsedStatement.from_statement_result(parse_result)

        resolved_account_id = _resolve_account_id(db, parse_result.statement_type, account_id)

        recon_result = ReconciliationService.reconcile(db, parsed, resolved_account_id)

        imported_count = 0
        classified_count = 0
        review_queue_count = 0

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
                        # Sync is_income with INCOME category
                        if classification.category == 'INCOME':
                            txn.is_income = True
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
                        classified_count += 1
                    else:
                        review_queue_count += 1
                except Exception as e:
                    logger.warning(f"Classification failed for {txn.merchant_raw}: {e}")
                    review_queue_count += 1

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
                    (Transaction.is_income == True) | (Transaction.type == 'credit'),
                ).with_entities(sa_func.coalesce(sa_func.sum(Transaction.amount), 0)).scalar()

                debit_sum = bal_query.filter(
                    Transaction.type == 'debit',
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
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Statement import failed: {e}")
        return {
            "statement_type": None,
            "total_parsed": 0,
            "matched": 0,
            "skipped_dup": 0,
            "possible": 0,
            "new_imported": 0,
            "imported": 0,
            "classified": 0,
            "review_queue": 0,
            "income_detected": 0,
            "income_items": [],
            "statement_closing_balance": None,
            "computed_balance": None,
            "balance_discrepancy": None,
            "errors": [f"Import could not be completed: {str(e)}"],
        }


# Keep legacy endpoint for backward compatibility
@router.post("/ingest/upload")
async def upload_statement_legacy(
    file: UploadFile = File(...),
    password: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Legacy single-step upload. Delegates to the import endpoint."""
    return await import_statement(
        file=file,
        password=password,
        account_id=None,
        import_new=True,
        detect_income=True,
        db=db,
        _user=_user,
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
