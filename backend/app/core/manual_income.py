from __future__ import annotations

import hashlib
import json
import uuid
from calendar import monthrange
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from app.core.audit import assert_period_writable
from app.core.money import money_decimal
from app.core.transaction_semantics import (
    TransactionSemantic,
    apply_transaction_semantic,
    infer_semantic_type,
)
from app.models.audit_log import AuditLog
from app.models.income_source import IncomeSource
from app.models.transaction import Transaction


@dataclass(frozen=True)
class ManualIncomeEntry:
    date: date
    amount: object


@dataclass(frozen=True)
class ManualIncomeRecordResult:
    created: tuple[Transaction, ...]
    skipped_existing: int


def link_manual_income_provenance(
    db: Session,
    transaction: Transaction,
    *,
    evidence_kind: str,
    evidence_id: str,
) -> bool:
    """Attach hashed source evidence to one exact manual-income match."""
    if (
        transaction.source != "manual_income"
        or transaction.semantic_type != TransactionSemantic.INCOME.value
    ):
        return False
    token = (
        f"reconciled_{evidence_kind}:"
        f"{hashlib.sha256(evidence_id.encode('utf-8')).hexdigest()}"
    )
    try:
        evidence = json.loads(transaction.extraction_evidence or "[]")
    except (TypeError, json.JSONDecodeError):
        evidence = []
    if not isinstance(evidence, list):
        evidence = []
    if token in evidence:
        transaction.reconciled = True
        return False
    evidence.append(token)
    transaction.extraction_evidence = json.dumps(
        [str(item)[:160] for item in evidence],
        separators=(",", ":"),
    )
    transaction.reconciled = True
    db.add(
        AuditLog(
            transaction_id=transaction.id,
            field_changed="income_reconciliation_evidence",
            old_value=None,
            new_value=token,
            change_source="system_reconcile",
        )
    )
    return True


def link_exact_statement_manual_income_matches(
    db: Session,
    matches: object,
    *,
    statement_fingerprint: str,
) -> int:
    linked = 0
    for match in matches:
        existing = getattr(match, "existing_txn", None)
        parsed = getattr(match, "parsed_txn", None)
        if (
            getattr(match, "match_type", None) != "exact"
            or existing is None
            or parsed is None
        ):
            continue
        parsed_semantic = getattr(parsed, "semantic_type", None)
        if parsed_semantic != TransactionSemantic.INCOME.value:
            parsed_semantic = infer_semantic_type(
                transaction_type=getattr(parsed, "type", ""),
                category=getattr(parsed, "category_hint", None),
                subcategory=getattr(parsed, "subcategory_hint", None),
                is_transfer=bool(getattr(parsed, "is_transfer", False)),
                text_parts=(getattr(parsed, "description", None),),
            )
        if parsed_semantic != TransactionSemantic.INCOME.value:
            continue
        linked += link_manual_income_provenance(
            db,
            existing,
            evidence_kind="statement",
            evidence_id=statement_fingerprint,
        )
    return linked


def monthly_income_entries(
    start_month: str,
    end_month: str,
    *,
    payment_day: int,
    amount: object,
) -> tuple[ManualIncomeEntry, ...]:
    start_year, start_number = map(int, start_month.split("-"))
    end_year, end_number = map(int, end_month.split("-"))
    start_index = start_year * 12 + start_number - 1
    end_index = end_year * 12 + end_number - 1
    if end_index < start_index:
        raise ValueError("End month must be the same as or after the start month")
    if end_index - start_index >= 120:
        raise ValueError("A single historical income entry is limited to 120 months")

    normalized_amount = money_decimal(amount)
    entries: list[ManualIncomeEntry] = []
    for index in range(start_index, end_index + 1):
        year, zero_based_month = divmod(index, 12)
        month = zero_based_month + 1
        day = min(payment_day, monthrange(year, month)[1])
        entry_date = date(year, month, day)
        if entry_date > date.today():
            raise ValueError("Actual income dates cannot be in the future")
        entries.append(ManualIncomeEntry(date=entry_date, amount=normalized_amount))
    return tuple(entries)


def manual_income_preview_fingerprint(
    entries: tuple[ManualIncomeEntry, ...],
    *,
    source_name: str,
    income_source_id: str | None,
    account_id: str,
    subcategory: str,
    note: str | None,
    reference: str | None,
) -> str:
    payload = {
        "account_id": account_id,
        "entries": [
            {"amount": str(money_decimal(entry.amount)), "date": entry.date.isoformat()}
            for entry in entries
        ],
        "income_source_id": income_source_id,
        "note": note,
        "reference": reference,
        "source_name": " ".join(source_name.split()),
        "subcategory": subcategory,
        "version": 1,
    }
    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _entry_checksum(
    entry: ManualIncomeEntry,
    *,
    source_name: str,
    income_source_id: str | None,
    account_id: str,
    subcategory: str,
) -> str:
    canonical = "|".join(
        (
            "manual-income-v1",
            account_id,
            entry.date.isoformat(),
            str(money_decimal(entry.amount)),
            " ".join(source_name.upper().split()),
            income_source_id or "",
            subcategory,
        )
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _semantic_detail(subcategory: str) -> str:
    if subcategory == "Salary":
        return "salary"
    if subcategory == "Interest":
        return "interest_credit"
    return "other_income"


def record_manual_income_entries(
    db: Session,
    entries: tuple[ManualIncomeEntry, ...],
    *,
    source_name: str,
    income_source: IncomeSource | None,
    account_id: str,
    subcategory: str,
    note: str | None,
    reference: str | None,
) -> ManualIncomeRecordResult:
    checked_periods: set[tuple[int, int]] = set()
    for entry in entries:
        period = (entry.date.year, entry.date.month)
        if period not in checked_periods:
            assert_period_writable(db, entry.date)
            checked_periods.add(period)

    normalized_source = " ".join(source_name.split())
    created: list[Transaction] = []
    skipped = 0
    for entry in entries:
        checksum = _entry_checksum(
            entry,
            source_name=normalized_source,
            income_source_id=income_source.id if income_source else None,
            account_id=account_id,
            subcategory=subcategory,
        )
        if db.query(Transaction.id).filter_by(checksum_source=checksum).first():
            skipped += 1
            continue
        transaction = Transaction(
            id=str(uuid.uuid4()),
            date=entry.date,
            raw_text=f"Manual income: {normalized_source}",
            merchant_raw=normalized_source,
            merchant_normalized=normalized_source.upper(),
            amount=entry.amount,
            type="credit",
            instrument="manual",
            account_id=account_id,
            category="INCOME",
            subcategory=subcategory,
            confidence=1.0,
            classification_source="user",
            status="settled",
            source="manual_income",
            semantic_detail=_semantic_detail(subcategory),
            reference_number=reference,
            extraction_evidence=json.dumps(
                [
                    "user_confirmed_manual_income",
                    *(
                        [f"income_source:{income_source.id}"]
                        if income_source
                        else []
                    ),
                ],
                separators=(",", ":"),
            ),
            review_required=False,
            checksum_source=checksum,
            notes=note,
            reconciled=False,
        )
        apply_transaction_semantic(transaction, TransactionSemantic.INCOME.value)
        db.add(transaction)
        db.flush()
        db.add(
            AuditLog(
                transaction_id=transaction.id,
                field_changed="manual_income_recorded",
                old_value=None,
                new_value=json.dumps(
                    {
                        "income_source_id": income_source.id if income_source else None,
                        "subcategory": subcategory,
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                change_source="user_income",
            )
        )
        created.append(transaction)

    if income_source and created:
        latest = max(created, key=lambda transaction: (transaction.date, transaction.id))
        income_source.last_detected_date = latest.date
        income_source.last_detected_amount = latest.amount
    db.flush()
    return ManualIncomeRecordResult(
        created=tuple(created),
        skipped_existing=skipped,
    )
