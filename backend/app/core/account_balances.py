"""Verified account balances derived from exact anchors and covered ledger rows."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, case, cast, func
from sqlalchemy.orm import Session

from app.core.money import MONEY_SCALE, money_decimal
from app.core.parser_metadata import PARSER_REGISTRY_VERSION
from app.core.transaction_semantics import active_clause
from app.models.account import Account
from app.models.account_balance import (
    AccountBalanceAnchor,
    AccountStatementCoverage,
)
from app.models.transaction import Transaction

if TYPE_CHECKING:
    from app.core.statement_parser import StatementParseResult


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class BalanceResult:
    balance: Decimal | None
    currency: str
    as_of: date
    status: str
    anchor_as_of: date | None
    coverage_complete: bool
    source: str | None
    missing_ranges: tuple[str, ...] = ()
    account_count: int = 1
    verified_account_count: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "balance": float(self.balance) if self.balance is not None else None,
            "currency": self.currency,
            "as_of": self.as_of.isoformat(),
            "status": self.status,
            "anchor_as_of": (
                self.anchor_as_of.isoformat() if self.anchor_as_of else None
            ),
            "coverage_complete": self.coverage_complete,
            "source": self.source,
            "missing_ranges": list(self.missing_ranges),
            "account_count": self.account_count,
            "verified_account_count": self.verified_account_count,
        }


def _exclusive_day(value: date) -> date:
    try:
        return value + timedelta(days=1)
    except OverflowError as exc:
        raise ValueError("Balance date is outside GODFIN's supported range") from exc


def _ledger_delta(
    db: Session,
    account_id: str,
    start_boundary: date,
    end_boundary: date,
) -> Decimal:
    if end_boundary <= start_boundary:
        return Decimal("0.00")
    amount_minor = cast(Transaction.__table__.c.amount_minor, BigInteger)
    signed_amount = case(
        (Transaction.type == "credit", amount_minor),
        (Transaction.type == "debit", -amount_minor),
        else_=0,
    )
    total_minor = (
        db.query(func.coalesce(func.sum(signed_amount), 0))
        .filter(
            Transaction.account_id == account_id,
            Transaction.date >= start_boundary,
            Transaction.date < end_boundary,
            active_clause(Transaction),
        )
        .scalar()
    )
    return (Decimal(int(total_minor or 0)) / MONEY_SCALE).quantize(
        Decimal("0.01")
    )


def _parsed_delta_before(
    parse_result: StatementParseResult,
    boundary: date,
) -> Decimal:
    total = Decimal("0.00")
    for transaction in parse_result.transactions:
        if transaction.date >= boundary:
            continue
        amount = money_decimal(transaction.amount)
        total += amount if transaction.txn_type == "credit" else -amount
    return total.quantize(Decimal("0.01"))


def _mark_anchor_conflict(
    db: Session,
    anchor: AccountBalanceAnchor,
) -> None:
    affected_coverages = (
        db.query(AccountStatementCoverage)
        .filter(
            (AccountStatementCoverage.opening_anchor_id == anchor.id)
            | (AccountStatementCoverage.closing_anchor_id == anchor.id)
        )
        .all()
    )
    linked_anchor_ids: set[str] = {anchor.id}
    for coverage in affected_coverages:
        coverage.verified_controls = False
        coverage.status = "conflict"
        if coverage.opening_anchor_id:
            linked_anchor_ids.add(coverage.opening_anchor_id)
        if coverage.closing_anchor_id:
            linked_anchor_ids.add(coverage.closing_anchor_id)
    for linked in (
        db.query(AccountBalanceAnchor)
        .filter(AccountBalanceAnchor.id.in_(linked_anchor_ids))
        .all()
    ):
        linked.verified = False
        linked.conflict = True


def record_verified_statement_controls(
    db: Session,
    account_id: str,
    parse_result: StatementParseResult,
) -> AccountStatementCoverage | None:
    """Persist verified controls once a complete statement import is accepted.

    The source file is never stored. Re-importing the same fingerprint is
    idempotent, while a contradictory anchor is retained and marked for review.
    """

    required = (
        parse_result.period_start,
        parse_result.period_end,
        parse_result.opening_balance,
        parse_result.closing_balance,
    )
    if (
        parse_result.reconciliation_status != "passed"
        or any(value is None for value in required)
        or not parse_result.transactions
    ):
        return None

    fingerprint = (parse_result.source_digest or "").strip().lower()
    if not _SHA256.fullmatch(fingerprint):
        raise ValueError("A verified statement requires a SHA-256 fingerprint")

    existing_coverage = (
        db.query(AccountStatementCoverage)
        .filter_by(account_id=account_id, source_fingerprint=fingerprint)
        .first()
    )
    if existing_coverage:
        return existing_coverage

    period_start = parse_result.period_start
    period_end = parse_result.period_end
    assert period_start is not None and period_end is not None
    if period_end < period_start:
        raise ValueError("Statement coverage ends before it starts")

    opening = money_decimal(parse_result.opening_balance)
    closing = money_decimal(parse_result.closing_balance)
    closing_boundary = _exclusive_day(period_end)
    existing_anchors = (
        db.query(AccountBalanceAnchor)
        .filter(
            AccountBalanceAnchor.account_id == account_id,
            AccountBalanceAnchor.boundary_date >= period_start,
            AccountBalanceAnchor.boundary_date <= closing_boundary,
            AccountBalanceAnchor.verified.is_(True),
            AccountBalanceAnchor.conflict.is_(False),
        )
        .all()
    )
    conflicting: list[AccountBalanceAnchor] = []
    for anchor in existing_anchors:
        expected = (
            opening + _parsed_delta_before(parse_result, anchor.boundary_date)
        ).quantize(Decimal("0.01"))
        if expected != money_decimal(anchor.balance):
            conflicting.append(anchor)

    has_conflict = bool(conflicting)
    for anchor in conflicting:
        _mark_anchor_conflict(db, anchor)

    anchor_values = (
        (
            "statement_opening",
            period_start,
            period_start,
            opening,
        ),
        (
            "statement_closing",
            period_end,
            closing_boundary,
            closing,
        ),
    )
    created: dict[str, AccountBalanceAnchor] = {}
    for anchor_type, as_of_date, boundary_date, balance in anchor_values:
        anchor = AccountBalanceAnchor(
            id=str(uuid.uuid4()),
            account_id=account_id,
            as_of_date=as_of_date,
            boundary_date=boundary_date,
            balance=balance,
            currency="INR",
            anchor_type=anchor_type,
            source_fingerprint=fingerprint,
            parser_profile=parse_result.parser_profile,
            parser_version=PARSER_REGISTRY_VERSION,
            statement_period_start=period_start,
            statement_period_end=period_end,
            verified=not has_conflict,
            conflict=has_conflict,
            verification_method=parse_result.reconciliation_method,
        )
        db.add(anchor)
        created[anchor_type] = anchor

    db.flush()
    coverage = AccountStatementCoverage(
        id=str(uuid.uuid4()),
        account_id=account_id,
        source_fingerprint=fingerprint,
        period_start=period_start,
        period_end=period_end,
        parser_profile=parse_result.parser_profile,
        parser_version=PARSER_REGISTRY_VERSION,
        verified_controls=not has_conflict,
        contains_running_balance=all(
            transaction.closing_balance is not None
            for transaction in parse_result.transactions
        ),
        transaction_count=len(parse_result.transactions),
        status="conflict" if has_conflict else "verified",
        opening_anchor_id=created["statement_opening"].id,
        closing_anchor_id=created["statement_closing"].id,
    )
    db.add(coverage)
    db.flush()
    return coverage


def _missing_coverage_ranges(
    db: Session,
    account_id: str,
    start_boundary: date,
    end_boundary: date,
) -> tuple[str, ...]:
    if end_boundary <= start_boundary:
        return ()
    rows = (
        db.query(AccountStatementCoverage)
        .filter(
            AccountStatementCoverage.account_id == account_id,
            AccountStatementCoverage.status == "verified",
            AccountStatementCoverage.verified_controls.is_(True),
            AccountStatementCoverage.period_end >= start_boundary,
            AccountStatementCoverage.period_start < end_boundary,
        )
        .order_by(AccountStatementCoverage.period_start)
        .all()
    )
    intervals = [
        (row.period_start, _exclusive_day(row.period_end))
        for row in rows
    ]
    cursor = start_boundary
    missing: list[str] = []
    for interval_start, interval_end in intervals:
        if interval_end <= cursor:
            continue
        if interval_start > cursor:
            gap_end = min(interval_start, end_boundary)
            if gap_end > cursor:
                missing.append(
                    f"{cursor.isoformat()}/{(gap_end - timedelta(days=1)).isoformat()}"
                )
            cursor = gap_end
        if interval_start <= cursor:
            cursor = max(cursor, min(interval_end, end_boundary))
        if cursor >= end_boundary:
            break
    if cursor < end_boundary:
        missing.append(
            f"{cursor.isoformat()}/{(end_boundary - timedelta(days=1)).isoformat()}"
        )
    return tuple(missing)


def balance_at_date(
    db: Session,
    account_id: str,
    as_of: date,
    *,
    allow_estimate: bool = False,
) -> BalanceResult:
    """Return an end-of-day balance only when its provenance is explicit."""

    cutoff = _exclusive_day(as_of)
    candidate_anchors = (
        db.query(AccountBalanceAnchor)
        .filter(
            AccountBalanceAnchor.account_id == account_id,
            AccountBalanceAnchor.boundary_date <= cutoff,
        )
        .order_by(
            AccountBalanceAnchor.boundary_date.desc(),
            AccountBalanceAnchor.created_at.desc(),
        )
        .all()
    )
    anchor = next(
        (
            candidate
            for candidate in candidate_anchors
            if candidate.verified and not candidate.conflict
        ),
        None,
    )
    if anchor is None:
        has_conflict = any(candidate.conflict for candidate in candidate_anchors)
        return BalanceResult(
            balance=None,
            currency="INR",
            as_of=as_of,
            status="conflict" if has_conflict else "unverified_no_anchor",
            anchor_as_of=None,
            coverage_complete=False,
            source=None,
        )

    if any(
        candidate.conflict
        and candidate.boundary_date >= anchor.boundary_date
        for candidate in candidate_anchors
    ):
        return BalanceResult(
            balance=None,
            currency=anchor.currency,
            as_of=as_of,
            status="conflict",
            anchor_as_of=anchor.as_of_date,
            coverage_complete=False,
            source=anchor.anchor_type,
        )
    reached_anchors = sorted(
        (
            candidate
            for candidate in candidate_anchors
            if candidate.boundary_date > anchor.boundary_date
            and candidate.verified
            and not candidate.conflict
        ),
        key=lambda candidate: candidate.boundary_date,
    )
    anchor_balance = money_decimal(anchor.balance)
    for reached in reached_anchors:
        expected = (
            anchor_balance
            + _ledger_delta(
                db,
                account_id,
                anchor.boundary_date,
                reached.boundary_date,
            )
        ).quantize(Decimal("0.01"))
        if expected != money_decimal(reached.balance):
            return BalanceResult(
                balance=None,
                currency=anchor.currency,
                as_of=as_of,
                status="conflict",
                anchor_as_of=anchor.as_of_date,
                coverage_complete=False,
                source=anchor.anchor_type,
            )

    missing = _missing_coverage_ranges(
        db,
        account_id,
        anchor.boundary_date,
        cutoff,
    )
    balance = (
        anchor_balance
        + _ledger_delta(db, account_id, anchor.boundary_date, cutoff)
    ).quantize(Decimal("0.01"))
    if missing and not allow_estimate:
        balance = None
    status = (
        "verified"
        if not missing
        else "estimated_partial"
        if allow_estimate
        else "unverified_gap"
    )
    return BalanceResult(
        balance=balance,
        currency=anchor.currency,
        as_of=as_of,
        status=status,
        anchor_as_of=anchor.as_of_date,
        coverage_complete=not missing,
        source=anchor.anchor_type,
        missing_ranges=missing,
        verified_account_count=1 if not missing else 0,
    )


def aggregate_balance_at_date(
    db: Session,
    as_of: date,
    *,
    allow_estimate: bool = False,
) -> BalanceResult:
    """Aggregate active savings accounts without hiding incomplete accounts."""

    accounts = (
        db.query(Account)
        .filter(Account.is_active.is_(True), Account.account_type == "savings")
        .order_by(Account.id)
        .all()
    )
    if not accounts:
        return BalanceResult(
            balance=None,
            currency="INR",
            as_of=as_of,
            status="unverified_no_accounts",
            anchor_as_of=None,
            coverage_complete=False,
            source=None,
            account_count=0,
        )

    results = [
        balance_at_date(db, account.id, as_of, allow_estimate=allow_estimate)
        for account in accounts
    ]
    verified = [result for result in results if result.status == "verified"]
    balances_available = all(result.balance is not None for result in results)
    complete = len(verified) == len(results)
    if complete:
        status = "verified"
    elif any(result.status == "conflict" for result in results):
        status = "conflict"
    elif allow_estimate and balances_available:
        status = "estimated_partial"
    elif any(result.status == "unverified_gap" for result in results):
        status = "unverified_gap"
    else:
        status = "unverified_no_anchor"
    total = (
        sum((result.balance or Decimal("0.00") for result in results), Decimal("0.00"))
        if (complete or (allow_estimate and balances_available))
        else None
    )
    anchors = [result.anchor_as_of for result in results if result.anchor_as_of]
    missing = tuple(
        dict.fromkeys(
            item
            for result in results
            for item in result.missing_ranges
        )
    )
    return BalanceResult(
        balance=total,
        currency="INR",
        as_of=as_of,
        status=status,
        anchor_as_of=min(anchors) if anchors else None,
        coverage_complete=complete,
        source="verified_account_anchors" if anchors else None,
        missing_ranges=missing,
        account_count=len(results),
        verified_account_count=len(verified),
    )
