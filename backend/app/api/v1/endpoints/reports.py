from __future__ import annotations

import csv
import io
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field, SecretStr, field_validator
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.csv_security import spreadsheet_safe_mapping, spreadsheet_safe_row
from app.core.database import get_db
from app.core.errors import IntegrationUnavailableError
from app.core.reporting import (
    DetailedReportUnavailable,
    generate_ai_financial_insights,
    generate_detailed_pdf,
    generate_summary_pdf,
    prepare_detailed_report,
    prepare_summary_report,
    set_savings_target_percent,
)
from app.core.tax_pack import build_financial_year_tax_pack
from app.core.transaction_semantics import (
    is_spending,
    is_verified_income,
    semantic_type_for,
)
from app.core.llm_privacy import has_hosted_data_consent, is_local_provider
from app.models.account import Account
from app.models.transaction import Transaction
from app.models.llm_config import LLMConfiguration
from app.schemas.financial import YearMonth

router = APIRouter()
AI_REPORT_CONSENT_VERSION = "2026-08-02"


class AIReportRequest(BaseModel):
    month: YearMonth | None = None
    consent: bool


class SavingsTargetRequest(BaseModel):
    target_percent: float = Field(ge=1, le=80)


class SavingsTargetResponse(BaseModel):
    target_percent: float
    minimum_percent: float
    maximum_percent: float
    applies_to: str


class TaxPackRequest(BaseModel):
    start_year: int = Field(ge=2000, le=2100)
    passphrase: SecretStr

    @field_validator("passphrase")
    @classmethod
    def validate_passphrase(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value()
        if not 12 <= len(raw) <= 128:
            raise ValueError("Passphrase must be between 12 and 128 characters")
        if any(ord(character) < 32 or ord(character) == 127 for character in raw):
            raise ValueError("Passphrase cannot contain control characters")
        return value


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
        "semantic_type": semantic_type_for(transaction),
        "source": transaction.source,
        "tags": transaction.tags,
        "notes": transaction.notes,
    }


@router.get("/summary")
def report_summary(
    month: YearMonth | None = None,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    if month is None:
        month = _default_month(db)
    return prepare_summary_report(db, month)


@router.get("/detailed")
def report_detailed(
    month: YearMonth | None = None,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    if month is None:
        month = _default_month(db)
    return prepare_detailed_report(db, month)


@router.put(
    "/preferences/savings-target",
    response_model=SavingsTargetResponse,
)
def update_report_savings_target(
    body: SavingsTargetRequest,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    target = set_savings_target_percent(db, body.target_percent)
    return {
        "target_percent": float(target),
        "minimum_percent": 1.0,
        "maximum_percent": 80.0,
        "applies_to": "completed monthly report target comparisons",
    }


def _ai_report_metadata(llm_config: LLMConfiguration) -> dict:
    local_provider = is_local_provider(llm_config.provider)
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
            'processing': 'on_device' if local_provider else 'hosted_provider',
            'shared': (
                [
                    'exact aggregate totals processed only by the local model',
                    'category summaries and aggregate trends processed on this device',
                ]
                if local_provider
                else [
                    'amount bands rather than exact financial amounts',
                    'ratios, counts, taxonomy categories, and aggregate trend direction',
                    'the report instructions needed to produce the requested explanation',
                ]
            ),
            'not_shared': [
                'account or card numbers',
                'raw transaction descriptions',
                'merchant names',
                'exact dates or exact financial amounts for hosted providers',
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
    if not has_hosted_data_consent(llm_config):
        raise HTTPException(
            status_code=409,
            detail="Accept the hosted AI data disclosure in Settings before continuing.",
        )
    month = body.month or _default_month(db)
    from app.core.reporting import _get_spending_trend
    detailed = prepare_detailed_report(db, month)
    trend = _get_spending_trend(db, month)
    try:
        insights = generate_ai_financial_insights(detailed, trend)
    except DetailedReportUnavailable as exc:
        raise IntegrationUnavailableError(
            code="AI_REPORT_UNAVAILABLE",
            message="The connected AI did not return a usable report.",
            hint="Standard totals and exports remain available. Try the analysis again later.",
        ) from exc
    metadata = _ai_report_metadata(llm_config)
    return {
        'month': month,
        'insights': insights,
        **metadata,
    }


@router.get("/pdf/summary")
def report_pdf_summary(
    month: YearMonth | None = None,
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
    month: YearMonth | None = None,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    if month is None:
        month = _default_month(db)

    year, mon = int(month[:4]), int(month[5:7])
    start = date(year, mon, 1)
    if mon == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, mon + 1, 1)

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
        writer.writerow(
            spreadsheet_safe_row(
                [
                    t.date.strftime('%Y-%m-%d') if t.date else '',
                    t.merchant_normalized or t.merchant_raw or '',
                    f'{t.amount:.2f}' if t.amount is not None else '',
                    t.type or '',
                    t.category or '',
                    t.subcategory or '',
                    _account_label(accounts.get(t.account_id)),
                    t.is_recurring,
                ]
            )
        )

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
            for transaction, row in zip(transactions, rows)
            if is_spending(transaction)
        )
        income = sum(
            row["amount"]
            for transaction, row in zip(transactions, rows)
            if is_verified_income(transaction)
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
        "is_transfer", "is_recurring", "is_income", "semantic_type", "source",
        "tags", "notes",
    ]
    writer = csv.DictWriter(output, fieldnames=columns)
    writer.writeheader()
    writer.writerows(spreadsheet_safe_mapping(row) for row in rows)
    return Response(
        content=output.getvalue().encode("utf-8"),
        media_type="text/csv",
        headers={
            "Content-Disposition": (
                f'attachment; filename="godfin_ca_{label.lower()}.csv"'
            )
        },
    )


@router.post("/fy/pack")
def report_financial_year_pack(
    body: TaxPackRequest,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Build an AES-256 encrypted, review-oriented Indian FY tax pack."""
    from app.api.v1.endpoints.license import enforce_feature

    enforce_feature(db, "advanced_reports")
    content = build_financial_year_tax_pack(
        db,
        body.start_year,
        passphrase=body.passphrase.get_secret_value(),
    )
    label = f"fy{body.start_year}-{str(body.start_year + 1)[-2:]}"
    return Response(
        content=content,
        media_type="application/zip",
        headers={
            "Content-Disposition": (
                f'attachment; filename="godfin_ca_tax_pack_{label}.zip"'
            ),
            "Cache-Control": "no-store",
            "Pragma": "no-cache",
            "X-Content-Type-Options": "nosniff",
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
    if not has_hosted_data_consent(llm_config):
        raise HTTPException(
            status_code=409,
            detail="Accept the hosted AI data disclosure in Settings before continuing.",
        )

    try:
        pdf_bytes = generate_detailed_pdf(
            db,
            month,
            ai_metadata=_ai_report_metadata(llm_config),
        )
    except DetailedReportUnavailable as exc:
        raise IntegrationUnavailableError(
            code="AI_REPORT_UNAVAILABLE",
            message="The connected AI could not create the detailed report.",
            hint="The standard summary report remains available.",
        ) from exc

    return Response(
        content=pdf_bytes,
        media_type='application/pdf',
        headers={
            'Content-Disposition': f'attachment; filename="godfin_detailed_{month}.pdf"',
        },
    )
