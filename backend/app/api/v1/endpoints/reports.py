from __future__ import annotations

import csv
import io
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.reporting import (
    DetailedReportUnavailable,
    generate_ai_financial_insights,
    generate_detailed_pdf,
    generate_summary_pdf,
    prepare_detailed_report,
    prepare_summary_report,
)
from app.core.tax_pack import build_financial_year_tax_pack
from app.models.account import Account
from app.models.transaction import Transaction
from app.models.llm_config import LLMConfiguration

router = APIRouter()
AI_REPORT_CONSENT_VERSION = "2026-08-02"


class AIReportRequest(BaseModel):
    month: str | None = Field(default=None, pattern=r'^\d{4}-\d{2}$')
    consent: bool


def _default_month(db: Session) -> str:
    """Latest month that contains non-deleted transactions, falling back to this month."""
    try:
        row = (
            db.query(func.max(Transaction.date))
            .filter(Transaction.status != 'deleted')
            .scalar()
        )
        if row:
            return f'{row.year}-{row.month:02d}'
    except Exception:
        pass
    today = date.today()
    return f'{today.year}-{today.month:02d}'


def _account_label(account: Account | None) -> str:
    if not account:
        return ""
    if account.nickname:
        return account.nickname
    return f"{account.bank} {account.account_type} (****{account.last_4_digits})"


def _transaction_export_row(
    transaction: Transaction, accounts: dict[str, Account]
) -> dict:
    account = accounts.get(transaction.account_id)
    return {
        "id": transaction.id,
        "date": transaction.date.isoformat() if transaction.date else None,
        "time": transaction.time.isoformat() if transaction.time else None,
        "merchant_raw": transaction.merchant_raw,
        "merchant": transaction.merchant_normalized,
        "raw_text": transaction.raw_text,
        "amount": round(float(transaction.amount), 2),
        "type": transaction.type,
        "instrument": transaction.instrument,
        "account": _account_label(account),
        "account_id": transaction.account_id,
        "category": transaction.category,
        "subcategory": transaction.subcategory,
        "confidence": transaction.confidence,
        "classification_source": transaction.classification_source,
        "status": transaction.status,
        "is_transfer": transaction.is_transfer,
        "is_recurring": transaction.is_recurring,
        "is_income": transaction.is_income,
        "source": transaction.source,
        "tags": transaction.tags,
        "notes": transaction.notes,
    }


@router.get("/summary")
def report_summary(
    month: str = Query(default=None, pattern=r'^\d{4}-\d{2}$'),
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    if month is None:
        month = _default_month(db)
    return prepare_summary_report(db, month)


@router.get("/detailed")
def report_detailed(
    month: str = Query(default=None, pattern=r'^\d{4}-\d{2}$'),
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    if month is None:
        month = _default_month(db)
    return prepare_detailed_report(db, month)


def _ai_report_metadata(llm_config: LLMConfiguration) -> dict:
    return {
        'generated_at': datetime.now(UTC).isoformat(),
        'llm': {
            'provider': llm_config.provider,
            'model': llm_config.model,
        },
        'consent': {
            'provided': True,
            'version': AI_REPORT_CONSENT_VERSION,
            'action': 'generate_ai_financial_report',
        },
        'data_disclosure': {
            'shared': [
                'exact monthly income, spending, and savings totals',
                'category and merchant aggregate totals',
                'recurring-payment summaries',
                'six months of aggregate income and spending trends',
            ],
            'not_shared': [
                'account or card numbers',
                'raw transaction descriptions',
                'transaction IDs or account IDs',
                'PIN, license key, or Gmail credentials',
            ],
        },
    }


@router.post("/ai/insights")
def report_ai_insights(
    body: AIReportRequest,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Structured, LLM-authored financial insights for the month."""
    from app.api.v1.endpoints.license import enforce_feature

    enforce_feature(db, "advanced_reports")
    if body.consent is not True:
        raise HTTPException(
            status_code=400,
            detail="Explicit consent is required before data is sent to an AI provider",
        )
    llm_config = db.query(LLMConfiguration).filter_by(is_active=True).first()
    if not llm_config:
        raise HTTPException(
            status_code=409,
            detail=(
                "Connect an AI in Settings to create a detailed analysis. "
                "Standard totals and exports remain available without AI."
            ),
        )
    month = body.month or _default_month(db)
    from app.core.reporting import _get_spending_trend
    detailed = prepare_detailed_report(db, month)
    trend = _get_spending_trend(db, month)
    try:
        insights = generate_ai_financial_insights(detailed, trend)
    except DetailedReportUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    metadata = _ai_report_metadata(llm_config)
    return {
        'month': month,
        'insights': insights,
        **metadata,
    }


@router.get("/pdf/summary")
def report_pdf_summary(
    month: str = Query(default=None, pattern=r'^\d{4}-\d{2}$'),
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    if month is None:
        month = _default_month(db)

    pdf_bytes = generate_summary_pdf(db, month)

    return Response(
        content=pdf_bytes,
        media_type='application/pdf',
        headers={
            'Content-Disposition': f'attachment; filename="godfin_summary_{month}.pdf"',
        },
    )


@router.get("/csv")
def report_csv(
    month: str = Query(default=None, pattern=r'^\d{4}-\d{2}$'),
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    if month is None:
        month = _default_month(db)

    year, mon = int(month[:4]), int(month[5:7])
    start = datetime(year, mon, 1)
    if mon == 12:
        end = datetime(year + 1, 1, 1)
    else:
        end = datetime(year, mon + 1, 1)

    txns = (
        db.query(Transaction)
        .filter(Transaction.date >= start, Transaction.date < end)
        .order_by(Transaction.date)
        .all()
    )

    # Build account lookup for human-readable names
    accounts = {a.id: a for a in db.query(Account).all()}

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'Date', 'Merchant', 'Amount', 'Type', 'Category',
        'Subcategory', 'Account', 'Is Recurring',
    ])
    for t in txns:
        writer.writerow([
            t.date.strftime('%Y-%m-%d') if t.date else '',
            t.merchant_normalized or t.merchant_raw or '',
            f'{t.amount:.2f}' if t.amount is not None else '',
            t.type or '',
            t.category or '',
            t.subcategory or '',
            _account_label(accounts.get(t.account_id)),
            t.is_recurring,
        ])

    csv_bytes = output.getvalue().encode('utf-8')
    return Response(
        content=csv_bytes,
        media_type='text/csv',
        headers={
            'Content-Disposition': f'attachment; filename="godfin_transactions_{month}.csv"',
        },
    )


@router.get("/fy")
def report_financial_year(
    start_year: int = Query(ge=2000, le=2100),
    format: str = Query(default="csv", pattern=r"^(csv|json)$"),
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Export an Indian financial year (April–March) for a CA."""
    from app.api.v1.endpoints.license import enforce_feature

    enforce_feature(db, "advanced_reports")
    start = date(start_year, 4, 1)
    end = date(start_year + 1, 4, 1)
    transactions = (
        db.query(Transaction)
        .filter(
            Transaction.date >= start,
            Transaction.date < end,
            Transaction.status != "deleted",
        )
        .order_by(Transaction.date, Transaction.time, Transaction.id)
        .all()
    )
    accounts = {account.id: account for account in db.query(Account).all()}
    rows = [_transaction_export_row(transaction, accounts) for transaction in transactions]
    label = f"FY{start_year}-{str(start_year + 1)[-2:]}"

    if format == "json":
        spend = sum(
            row["amount"]
            for row in rows
            if row["type"] == "debit" and not row["is_transfer"]
        )
        income = sum(
            row["amount"]
            for row in rows
            if row["is_income"] and not row["is_transfer"]
        )
        return {
            "financial_year": label,
            "start_date": start.isoformat(),
            "end_date_exclusive": end.isoformat(),
            "generated_at": datetime.now().isoformat(),
            "summary": {
                "transaction_count": len(rows),
                "total_spend": round(spend, 2),
                "total_income": round(income, 2),
                "net": round(income - spend, 2),
            },
            "transactions": rows,
        }

    if format != "csv":
        raise HTTPException(status_code=400, detail="Format must be csv or json")
    output = io.StringIO()
    columns = [
        "id", "date", "time", "merchant_raw", "merchant", "raw_text",
        "amount", "type", "instrument", "account", "account_id", "category",
        "subcategory", "confidence", "classification_source", "status",
        "is_transfer", "is_recurring", "is_income", "source", "tags", "notes",
    ]
    writer = csv.DictWriter(output, fieldnames=columns)
    writer.writeheader()
    writer.writerows(rows)
    return Response(
        content=output.getvalue().encode("utf-8"),
        media_type="text/csv",
        headers={
            "Content-Disposition": (
                f'attachment; filename="godfin_ca_{label.lower()}.csv"'
            )
        },
    )


@router.get("/fy/pack")
def report_financial_year_pack(
    start_year: int = Query(ge=2000, le=2100),
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Build the review-oriented Indian FY ZIP tax pack for a CA."""
    from app.api.v1.endpoints.license import enforce_feature

    enforce_feature(db, "advanced_reports")
    content = build_financial_year_tax_pack(db, start_year)
    label = f"fy{start_year}-{str(start_year + 1)[-2:]}"
    return Response(
        content=content,
        media_type="application/zip",
        headers={
            "Content-Disposition": (
                f'attachment; filename="godfin_ca_tax_pack_{label}.zip"'
            )
        },
    )


@router.post("/pdf/detailed")
def report_pdf_detailed(
    body: AIReportRequest,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    from app.api.v1.endpoints.license import enforce_feature

    enforce_feature(db, "advanced_reports")
    if body.consent is not True:
        raise HTTPException(
            status_code=400,
            detail="Explicit consent is required before data is sent to an AI provider",
        )
    month = body.month or _default_month(db)
    llm_config = db.query(LLMConfiguration).filter_by(is_active=True).first()
    if not llm_config:
        raise HTTPException(
            status_code=409,
            detail=(
                "Connect an AI in Settings before creating the detailed report. "
                "The standard summary report remains available."
            ),
        )

    try:
        pdf_bytes = generate_detailed_pdf(
            db,
            month,
            ai_metadata=_ai_report_metadata(llm_config),
        )
    except DetailedReportUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return Response(
        content=pdf_bytes,
        media_type='application/pdf',
        headers={
            'Content-Disposition': f'attachment; filename="godfin_detailed_{month}.pdf"',
        },
    )
