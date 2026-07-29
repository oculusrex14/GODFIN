from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from time import perf_counter

from app.core.reconciliation import import_new_transactions
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
