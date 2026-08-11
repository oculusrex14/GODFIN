from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path
from time import perf_counter

from sqlalchemy import event

from app.api.v1.endpoints.dashboard import dashboard_stats
from app.core.behavior_insights import compute_behavior_insights
from app.core.reconciliation import import_new_transactions
from app.core.recurring import detect_recurring_patterns
from app.core.reporting import prepare_summary_report
from app.core.statement_parser import ParsedTransaction
from app.models.transaction import Transaction
from app.seed import SAVINGS_ACCOUNT_ID


_BUDGETS = json.loads(
    (
        Path(__file__).resolve().parents[2]
        / "performance"
        / "budgets.json"
    ).read_text(encoding="utf-8")
)


def _effective_limit(name: str) -> float:
    budget = _BUDGETS["budgets"][name]
    regression_limit = budget["accepted_baseline"] * (
        1 + _BUDGETS["regression_margin"]
    )
    return min(budget["absolute_max"], regression_limit)


@contextmanager
def _select_counter(db_session):
    engine = db_session.get_bind()
    count = 0

    def count_select(_conn, _cursor, statement, _params, _context, _many):
        nonlocal count
        if statement.lstrip().upper().startswith("SELECT"):
            count += 1

    event.listen(engine, "before_cursor_execute", count_select)
    try:
        yield lambda: count
    finally:
        event.remove(engine, "before_cursor_execute", count_select)


def _large_ledger(db_session, *, rows: int = 10_000) -> None:
    transactions = []
    for index in range(rows):
        is_income = index % 5 == 0
        merchant = (
            f"SYNTHETIC EMPLOYER {index % 8}"
            if is_income
            else f"SYNTHETIC MERCHANT {index % 250}"
        )
        transactions.append(
            Transaction(
                date=date(2026, 7, 1) + timedelta(days=index % 31),
                raw_text=merchant,
                merchant_raw=merchant,
                merchant_normalized=merchant,
                amount=5000 if is_income else (index % 900) + 100,
                type="credit" if is_income else "debit",
                instrument="statement",
                account_id=SAVINGS_ACCOUNT_ID,
                category="INCOME" if is_income else "SHOPPING",
                subcategory="Salary" if is_income else "General",
                status="settled",
                source="performance_fixture",
                is_income=is_income,
                semantic_type="income" if is_income else "expense",
            )
        )
    db_session.bulk_save_objects(transactions)
    db_session.commit()


def _record_measurement(name: str, elapsed_ms: float, selects: int) -> None:
    if os.environ.get("GODFIN_PRINT_PERF") == "1":
        print(
            json.dumps(
                {
                    "operation": name,
                    "elapsed_ms": round(elapsed_ms, 2),
                    "selects": selects,
                },
                sort_keys=True,
            )
        )


def test_filter_10000_transactions_stays_within_budget(
    auth_client,
    db_session,
):
    transactions = []
    for index in range(10_000):
        target = index % 997 == 0
        merchant = (
            f"PERFORMANCE TARGET {index}"
            if target
            else f"SYNTHETIC MERCHANT {index}"
        )
        transactions.append(
            Transaction(
                date=date(2026, 1, 1) + timedelta(days=index % 365),
                raw_text=merchant,
                merchant_raw=merchant,
                merchant_normalized=merchant,
                amount=float(index + 1),
                type="debit",
                instrument="statement",
                account_id=SAVINGS_ACCOUNT_ID,
                category="SHOPPING",
                subcategory="General",
                status="settled",
                source="performance_fixture",
            )
        )
    db_session.bulk_save_objects(transactions)
    db_session.commit()

    started = perf_counter()
    response = auth_client.get(
        "/api/v1/transactions",
        params={"search": "PERFORMANCE TARGET", "page_size": 50},
    )
    elapsed_ms = (perf_counter() - started) * 1000

    assert response.status_code == 200
    assert response.json()["total"] == 11
    assert elapsed_ms <= _effective_limit("transaction_filter_10000_ms"), (
        f"10,000-row filter took {elapsed_ms:.1f} ms; "
        f"limit is {_effective_limit('transaction_filter_10000_ms'):.1f} ms"
    )


def test_import_1000_structured_rows_stays_within_budget(db_session):
    transactions = [
        ParsedTransaction(
            date=date(2024, 1, 1) + timedelta(days=index % 365),
            description=f"PERFORMANCE IMPORT {index}",
            amount=float(index + 1),
            type="debit",
        )
        for index in range(1_000)
    ]

    started = perf_counter()
    imported = import_new_transactions(
        db_session,
        transactions,
        SAVINGS_ACCOUNT_ID,
        source="performance_fixture",
    )
    elapsed_ms = (perf_counter() - started) * 1000

    assert len(imported) == 1_000
    assert elapsed_ms <= _effective_limit("structured_import_1000_ms"), (
        f"1,000-row import took {elapsed_ms:.1f} ms; "
        f"limit is {_effective_limit('structured_import_1000_ms'):.1f} ms"
    )


def test_large_ledger_read_paths_have_latency_and_query_budgets(db_session):
    _large_ledger(db_session)

    with _select_counter(db_session) as selected:
        started = perf_counter()
        dashboard = dashboard_stats(
            month="2026-07",
            period="full",
            db=db_session,
            _user=True,
        )
        elapsed_ms = (perf_counter() - started) * 1000
        dashboard_selects = selected()
    _record_measurement("dashboard_10000", elapsed_ms, dashboard_selects)
    assert dashboard.month_spend > 0
    assert elapsed_ms <= _effective_limit("dashboard_10000_ms")
    assert dashboard_selects <= _effective_limit("dashboard_10000_selects")

    db_session.expire_all()
    with _select_counter(db_session) as selected:
        started = perf_counter()
        report = prepare_summary_report(
            db_session,
            "2026-07",
            as_of=date(2026, 8, 1),
        )
        elapsed_ms = (perf_counter() - started) * 1000
        report_selects = selected()
    _record_measurement("report_summary_10000", elapsed_ms, report_selects)
    assert report["transaction_count"] == 8_000
    assert elapsed_ms <= _effective_limit("report_summary_10000_ms")
    assert report_selects <= _effective_limit("report_summary_10000_selects")

    db_session.expire_all()
    with _select_counter(db_session) as selected:
        started = perf_counter()
        insights = compute_behavior_insights(
            db_session,
            today=date(2026, 8, 1),
        )
        elapsed_ms = (perf_counter() - started) * 1000
        insight_selects = selected()
    _record_measurement("behavior_insights_10000", elapsed_ms, insight_selects)
    assert len(insights["metrics"]) >= 7
    assert elapsed_ms <= _effective_limit("behavior_insights_10000_ms")
    assert insight_selects <= _effective_limit("behavior_insights_10000_selects")


def test_recurring_detection_1000_merchants_has_bounded_reads_and_latency(
    db_session,
):
    transactions = []
    start = date(2026, 1, 31)
    for merchant_index in range(1_000):
        merchant = f"SYNTHETIC RECURRING {merchant_index:04d}"
        for month_offset in range(4):
            month_index = start.year * 12 + start.month - 1 + month_offset
            year = month_index // 12
            month = month_index % 12 + 1
            day = 28 if month == 2 else 30 if month in {4, 6, 9, 11} else 31
            transactions.append(
                Transaction(
                    date=date(year, month, day),
                    raw_text=merchant,
                    merchant_raw=merchant,
                    merchant_normalized=merchant,
                    amount=499 + merchant_index % 20,
                    type="debit",
                    instrument="statement",
                    account_id=SAVINGS_ACCOUNT_ID,
                    category="ENTERTAINMENT",
                    subcategory="Subscriptions",
                    status="settled",
                    source="performance_fixture",
                    semantic_type="expense",
                )
            )
    db_session.bulk_save_objects(transactions)
    db_session.commit()

    with _select_counter(db_session) as selected:
        started = perf_counter()
        summary = detect_recurring_patterns(
            db_session,
            as_of=date(2026, 5, 1),
        )
        db_session.commit()
        elapsed_ms = (perf_counter() - started) * 1000
        select_count = selected()
    _record_measurement(
        "recurring_detection_1000_merchants",
        elapsed_ms,
        select_count,
    )
    assert summary.scanned == 1_000
    assert summary.created == 1_000
    assert elapsed_ms <= _effective_limit("recurring_detection_1000_merchants_ms")
    assert select_count <= _effective_limit(
        "recurring_detection_1000_merchants_selects"
    )
