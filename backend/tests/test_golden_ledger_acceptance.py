from __future__ import annotations

import io
import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pyzipper

from app.core.account_balances import record_verified_statement_controls
from app.core.audit import finalize_audit, start_audit
from app.core.fx import FRANKFURTER_RATES_URL, FX_PROVIDER, FxRateSnapshot
from app.core.reconciliation import ReconciliationService
from app.core.statement_parser import (
    ParsedStatement,
    ParsedTransaction,
    StatementMetadata,
    StatementParseResult,
    StatementTransaction,
)
from app.core.time import utcnow_naive
from app.models.account_balance import AccountStatementCoverage
from app.models.income_source import IncomeSource
from app.models.llm_config import LLMConfiguration
from app.models.monthly_aggregate import MonthlyAggregate
from app.models.net_worth import NetWorthItem, NetWorthQuote
from app.models.recurring_pattern import RecurringPattern
from app.models.subscription import Subscription
from app.models.transaction import Transaction
from app.seed import CC_ACCOUNT_ID, SAVINGS_ACCOUNT_ID
from tests.golden_ledger_oracle import calculate_expected, normalize_expected
from tests.license_helpers import install_test_license


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "golden_ledger_v1.json"
TAX_PACK_PASSPHRASE = "Golden-Ledger-Archive-2026"
ROLE_TO_SEMANTIC = {
    "verified_income": "income",
    "spend": "expense",
    "non_income_credit": "unknown",
    "refund": "refund",
    "cashback": "cashback",
    "reimbursement": "reimbursement",
    "excluded": "reversal",
    "transfer": "internal_transfer",
}


def _fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _money(value: object) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


def _assert_money(actual: object, expected: object) -> None:
    assert _money(actual) == _money(expected)


def _seed_transactions(db, fixture: dict) -> dict[str, Transaction]:
    accounts = {"savings": SAVINGS_ACCOUNT_ID, "card": CC_ACCOUNT_ID}
    seeded: dict[str, Transaction] = {}
    for row in fixture["transactions"]:
        semantic = ROLE_TO_SEMANTIC[row["role"]]
        transaction = Transaction(
            id=row["id"],
            date=date.fromisoformat(row["date"]),
            raw_text=f"Golden ledger: {row['merchant']}",
            merchant_raw=row["merchant"],
            merchant_normalized=row["merchant"],
            amount=Decimal(row["amount"]),
            type=row["direction"],
            instrument="statement",
            account_id=accounts[row["account"]],
            category=row["category"],
            subcategory=row["subcategory"],
            confidence=Decimal("1.0"),
            classification_source="golden_fixture",
            status=row.get("status", "settled"),
            is_transfer=semantic == "internal_transfer",
            is_recurring=bool(row.get("recurring")),
            is_income=semantic == "income",
            semantic_type=semantic,
            semantic_detail=(
                "credit_card_payment"
                if row["id"].startswith("card-payment")
                else "internal_transfer"
                if semantic == "internal_transfer"
                else "salary"
                if row["id"].startswith("salary")
                else "other_income"
                if semantic == "income"
                else semantic
                if semantic in {"refund", "reversal"}
                else "purchase"
            ),
            source=row["source"],
            source_bank="synthetic",
            source_format_version="golden-ledger-v1",
            parser_version="golden-ledger-v1",
            upi_ref_number=row.get("reference"),
            reconciled=row["source"] == "statement_upload",
            review_required=False,
        )
        db.add(transaction)
        seeded[row["id"]] = transaction
    db.flush()
    return seeded


def _seed_income_sources(db, fixture: dict) -> None:
    for row in fixture["income_sources"]:
        db.add(
            IncomeSource(
                id=row["id"],
                source_name=row["name"],
                expected_amount=Decimal(row["amount"]),
                frequency=row["frequency"],
                effective_from=date.fromisoformat(row["effective_from"]),
                effective_to=(
                    date.fromisoformat(row["effective_to"])
                    if row.get("effective_to")
                    else None
                ),
                next_expected_date=(
                    date.fromisoformat(row["next_expected_date"])
                    if row.get("next_expected_date")
                    else None
                ),
                is_active=True,
                account_id=SAVINGS_ACCOUNT_ID,
                confirmed_merchant_alias="SYNTHETIC",
            )
        )


def _seed_subscriptions_and_recurring(db, fixture: dict) -> None:
    now = utcnow_naive()
    for row in fixture["subscriptions"]:
        foreign = row["currency"] != "INR"
        db.add(
            Subscription(
                id=row["id"],
                name=row["name"],
                amount=Decimal(row["amount"]),
                currency=row["currency"],
                frequency=row["frequency"],
                category=row["category"],
                is_active=True,
                fx_rate_to_inr=(Decimal(row["fx_to_inr"]) if foreign else None),
                fx_rate_source=(FX_PROVIDER if foreign else None),
                fx_rate_source_url=(FRANKFURTER_RATES_URL if foreign else None),
                fx_rate_as_of=(date.today() if foreign else None),
                fx_rate_fetched_at=(now if foreign else None),
            )
        )
    db.add(
        RecurringPattern(
            id="golden-recurring-pattern",
            merchant_normalized="SYNTHETIC STREAM",
            account_id=SAVINGS_ACCOUNT_ID,
            avg_amount=Decimal("1000.00"),
            amount_stddev=Decimal("0.00"),
            frequency="monthly",
            avg_interval_days=30,
            last_occurrence=date(2026, 7, 7),
            next_expected=date(2026, 8, 7),
            times_detected=3,
            category="ENTERTAINMENT",
            confidence=1.0,
            evidence_count=3,
            evidence_transaction_ids_json=json.dumps(["subscription-ledger-2026-07"]),
            detection_version="golden-v1",
            interval_variability=0.0,
            amount_variability=0.0,
            detection_status="active",
            is_active=True,
        )
    )


def _seed_net_worth(db, fixture: dict) -> None:
    now = utcnow_naive()
    for row in fixture["net_worth"]:
        if row["valuation_mode"] == "manual":
            item = NetWorthItem(
                id=row["id"],
                name=row["name"],
                item_type=row["item_type"],
                asset_class=("cash" if row["item_type"] == "asset" else "debt"),
                valuation_mode="manual",
                quantity=Decimal("1"),
                currency=row["currency"],
                manual_value=Decimal(row["native_value"]),
                exchange_rate_to_base=Decimal(row["fx_to_base"]),
                valuation_source="Golden ledger synthetic valuation",
                valued_at=date.today(),
                expires_on=date.today() + timedelta(days=30),
            )
            db.add(item)
            continue
        item = NetWorthItem(
            id=row["id"],
            name=row["name"],
            item_type=row["item_type"],
            asset_class="stock",
            valuation_mode="market",
            symbol="SYNTH",
            quantity=Decimal(row["quantity"]),
            currency=row["currency"],
        )
        db.add(item)
        db.flush()
        db.add(
            NetWorthQuote(
                id="golden-usd-quote",
                item_id=item.id,
                unit_price=Decimal(row["unit_price"]),
                quote_currency=row["currency"],
                exchange_rate_to_base=Decimal(row["fx_to_base"]),
                total_value_base=Decimal("8300.00"),
                base_currency="INR",
                source="Golden ledger fixed quote",
                source_url="https://example.invalid/golden-ledger",
                fx_rate_source=FX_PROVIDER,
                fx_rate_source_url=FRANKFURTER_RATES_URL,
                fx_rate_as_of=date.today(),
                fx_rate_fetched_at=now,
                quoted_at=now,
                expires_at=now + timedelta(days=1),
            )
        )


def _parsed_statement(*transaction_ids: str, fixture: dict) -> ParsedStatement:
    rows = {row["id"]: row for row in fixture["transactions"]}
    parsed = []
    for transaction_id in transaction_ids:
        row = rows[transaction_id]
        parsed.append(
            ParsedTransaction(
                date=date.fromisoformat(row["date"]),
                description=row["merchant"],
                amount=float(Decimal(row["amount"])),
                type=row["direction"],
                reference=row.get("reference"),
            )
        )
    return ParsedStatement(
        metadata=StatementMetadata(
            statement_type="golden_savings",
            statement_period="synthetic overlap",
        ),
        transactions=parsed,
    )


def _control_statement(
    *,
    fingerprint: str,
    period_start: date,
    period_end: date,
    opening: Decimal,
    amount: Decimal,
    transaction_type: str,
) -> StatementParseResult:
    closing = opening + amount if transaction_type == "credit" else opening - amount
    return StatementParseResult(
        transactions=[
            StatementTransaction(
                date=period_end,
                description="Golden statement control",
                amount=float(amount),
                txn_type=transaction_type,
                closing_balance=float(closing),
            )
        ],
        statement_type="golden_savings",
        parser_profile="golden_savings",
        recognized=True,
        reconciliation_status="passed",
        reconciliation_method="synthetic_running_balance",
        source_digest=fingerprint,
        period_start=period_start,
        period_end=period_end,
        opening_balance=float(opening),
        closing_balance=float(closing),
        total_debits=float(amount if transaction_type == "debit" else 0),
        total_credits=float(amount if transaction_type == "credit" else 0),
    )


def _fixed_fx_snapshot() -> FxRateSnapshot:
    return FxRateSnapshot(
        rates_to_inr={"INR": 1.0, "USD": 83.0},
        as_of=date.today(),
        provider=FX_PROVIDER,
        source_url=FRANKFURTER_RATES_URL,
        age_days=0,
        stale=False,
        status="available",
        rate_dates_to_inr={"INR": date.today(), "USD": date.today()},
    )


def _valid_llm_report() -> str:
    return json.dumps(
        {
            "executive_summary": "Synthetic commentary only.",
            "sections": [
                {
                    "title": "Synthetic overview",
                    "tone": "neutral",
                    "icon": "pie",
                    "content": "Authoritative totals remain in GODFIN calculations.",
                }
            ],
            "highlights": [],
            "recommendations": ["Review the deterministic totals."],
        }
    )


def test_golden_ledger_matches_independent_oracle_across_every_surface(
    auth_client,
    db_session,
    monkeypatch,
):
    fixture = _fixture()
    expected = fixture["expected"]
    assert normalize_expected(calculate_expected(fixture)) == expected

    install_test_license(db_session, "max")
    seeded = _seed_transactions(db_session, fixture)
    _seed_income_sources(db_session, fixture)
    _seed_subscriptions_and_recurring(db_session, fixture)
    _seed_net_worth(db_session, fixture)
    db_session.commit()

    # Manual history remains singular when one later and one overlapping
    # statement both contain the same events. Reconciliation never inserts a
    # second salary row.
    before_reconciliation = db_session.query(Transaction).count()
    june = ReconciliationService.reconcile(
        db_session,
        _parsed_statement("salary-2026-06", fixture=fixture),
        SAVINGS_ACCOUNT_ID,
    )
    overlap = ReconciliationService.reconcile(
        db_session,
        _parsed_statement(
            "salary-2026-06", "salary-2026-07", fixture=fixture
        ),
        SAVINGS_ACCOUNT_ID,
    )
    duplicate_import = ReconciliationService.reconcile(
        db_session,
        _parsed_statement("salary-2026-07", fixture=fixture),
        SAVINGS_ACCOUNT_ID,
    )
    assert (len(june.duplicate_transactions), june.total_new) == (1, 0)
    assert (len(overlap.duplicate_transactions), overlap.total_new) == (2, 0)
    assert (len(duplicate_import.duplicate_transactions), duplicate_import.total_new) == (1, 0)
    assert db_session.query(Transaction).count() == before_reconciliation

    # A contradictory overlapping statement control invalidates both anchors;
    # it is never silently presented as a verified account balance.
    first_control = _control_statement(
        fingerprint="a" * 64,
        period_start=date(2026, 3, 1),
        period_end=date(2026, 3, 31),
        opening=Decimal("1000.00"),
        amount=Decimal("100.00"),
        transaction_type="debit",
    )
    conflicting_control = _control_statement(
        fingerprint="b" * 64,
        period_start=date(2026, 2, 1),
        period_end=date(2026, 2, 28),
        opening=Decimal("499.00"),
        amount=Decimal("500.00"),
        transaction_type="credit",
    )
    record_verified_statement_controls(db_session, SAVINGS_ACCOUNT_ID, first_control)
    record_verified_statement_controls(
        db_session, SAVINGS_ACCOUNT_ID, conflicting_control
    )
    db_session.commit()
    assert (
        db_session.query(AccountStatementCoverage)
        .filter_by(status="conflict")
        .count()
        == 2
    )

    goal = auth_client.post(
        "/api/v1/goals",
        json={
            "name": fixture["goal"]["name"],
            "target_amount": float(Decimal(fixture["goal"]["target"])),
            "deadline_date": "2027-12-31",
            "current_saved": 0,
        },
    )
    assert goal.status_code == 201, goal.text
    goal_id = goal.json()["id"]
    for index, entry in enumerate(fixture["goal"]["entries"]):
        response = auth_client.post(
            f"/api/v1/goals/{goal_id}/contributions",
            json={
                "amount": float(abs(Decimal(entry["amount"]))),
                "entry_type": entry["type"],
                "contribution_date": "2026-08-01",
                "idempotency_key": f"golden-goal-{index}",
            },
        )
        assert response.status_code == 201, response.text

    audit_session = start_audit(db_session, 2026, 7)
    db_session.flush()
    finalize_audit(db_session, audit_session.id)
    db_session.commit()

    dashboard = auth_client.get(
        "/api/v1/dashboard/stats", params={"month": fixture["month"]}
    )
    assert dashboard.status_code == 200, dashboard.text
    dashboard_data = dashboard.json()
    _assert_money(dashboard_data["month_income"], expected["month"]["income"])
    _assert_money(dashboard_data["month_spend"], expected["month"]["spend"])
    assert str(dashboard_data["savings_rate"]) == expected["month"]["savings_rate"]
    assert dashboard_data["account_balance_status"] == "conflict"

    transactions = auth_client.get(
        "/api/v1/transactions",
        params={
            "date_from": "2026-07-01",
            "date_to": "2026-07-31",
            "page_size": 200,
        },
    )
    assert transactions.status_code == 200, transactions.text
    assert transactions.json()["total"] == expected["month"]["listed_transaction_count"]
    returned = {item["id"]: item for item in transactions.json()["items"]}
    assert returned["generic-credit-2026-07"]["is_income"] is False
    assert returned["refund-2026-07"]["semantic_type"] == "refund"
    assert returned["cashback-2026-07"]["semantic_type"] == "cashback"
    assert returned["reimbursement-2026-07"]["semantic_type"] == "reimbursement"
    assert returned["card-payment-2026-07"]["is_transfer"] is True

    cash_flow = auth_client.get(
        "/api/v1/cash-flow/calendar", params={"month": fixture["month"]}
    )
    assert cash_flow.status_code == 200, cash_flow.text
    _assert_money(cash_flow.json()["total_income"], expected["month"]["income"])
    _assert_money(cash_flow.json()["total_spend"], expected["month"]["spend"])
    _assert_money(cash_flow.json()["net"], expected["month"]["net"])

    report = auth_client.get(
        "/api/v1/reports/summary", params={"month": fixture["month"]}
    )
    assert report.status_code == 200, report.text
    report_data = report.json()
    _assert_money(report_data["total_income"], expected["month"]["income"])
    _assert_money(report_data["total_spend"], expected["month"]["spend"])
    assert report_data["transaction_count"] == expected["month"]["spending_count"]
    _assert_money(report_data["recurring_total"], "1000.00")

    tax_pack = auth_client.post(
        "/api/v1/reports/fy/pack",
        json={
            "start_year": fixture["financial_year_start"],
            "passphrase": TAX_PACK_PASSPHRASE,
        },
    )
    assert tax_pack.status_code == 200, tax_pack.text
    with pyzipper.AESZipFile(io.BytesIO(tax_pack.content)) as archive:
        archive.setpassword(TAX_PACK_PASSPHRASE.encode())
        tax_summary = json.loads(archive.read("reconciliation_summary.json"))
    _assert_money(
        tax_summary["income_candidate_total_inr"],
        expected["financial_year"]["income"],
    )
    _assert_money(
        tax_summary["expense_review_total_inr"],
        expected["financial_year"]["spend"],
    )
    assert tax_summary["transaction_count"] == expected["financial_year"]["transaction_count"]

    july_income = auth_client.get(
        "/api/v1/income/stats", params={"month": "2026-07"}
    )
    august_income = auth_client.get(
        "/api/v1/income/stats", params={"month": "2026-08"}
    )
    assert july_income.status_code == august_income.status_code == 200
    _assert_money(
        july_income.json()["total_expected_monthly"],
        expected["income_sources"]["july_expected"],
    )
    _assert_money(
        july_income.json()["total_detected_this_month"],
        expected["month"]["income"],
    )
    _assert_money(
        august_income.json()["total_expected_monthly"],
        expected["income_sources"]["august_expected"],
    )
    assert july_income.json()["sources_count"] == expected["income_sources"]["source_count"]

    profile = auth_client.get("/api/v1/profile")
    assert profile.status_code == 200, profile.text
    profile_data = profile.json()
    assert profile_data["period_start"] == "2026-07-01"
    _assert_money(profile_data["verified_income_total"], expected["month"]["income"])
    _assert_money(profile_data["spending_total"], expected["month"]["spend"])
    assert profile_data["verified_income_count"] == 2
    assert profile_data["spending_transaction_count"] == expected["month"]["spending_count"]
    assert str(profile_data["savings_rate"]) == expected["month"]["savings_rate"]

    snapshot = _fixed_fx_snapshot()

    async def fixed_subscription_rates(*_args, **_kwargs):
        return snapshot

    monkeypatch.setattr(
        "app.api.v1.endpoints.subscriptions._fetch_exchange_rates",
        fixed_subscription_rates,
    )
    subscriptions = auth_client.get("/api/v1/subscriptions/stats")
    assert subscriptions.status_code == 200, subscriptions.text
    _assert_money(
        subscriptions.json()["total_monthly_cost"],
        expected["subscriptions"]["monthly"],
    )
    _assert_money(
        subscriptions.json()["total_annual_projection"],
        expected["subscriptions"]["annual"],
    )
    assert subscriptions.json()["active_count"] == expected["subscriptions"]["active_count"]

    goals = auth_client.get("/api/v1/goals")
    assert goals.status_code == 200, goals.text
    golden_goal = next(item for item in goals.json() if item["id"] == goal_id)
    _assert_money(golden_goal["current_saved"], expected["goal"]["balance"])
    assert golden_goal["contribution_count"] == expected["goal"]["entry_count"]

    monkeypatch.setattr("app.core.net_worth.get_inr_rates", lambda *_a, **_kw: snapshot)
    net_worth = auth_client.get("/api/v1/net-worth")
    assert net_worth.status_code == 200, net_worth.text
    _assert_money(net_worth.json()["total_assets"], expected["net_worth"]["assets"])
    _assert_money(
        net_worth.json()["total_liabilities"], expected["net_worth"]["liabilities"]
    )
    _assert_money(net_worth.json()["net_worth"], expected["net_worth"]["net"])
    assert net_worth.json()["item_count"] == expected["net_worth"]["item_count"]

    audit = auth_client.get(
        "/api/v1/audit/month-status", params={"year": 2026, "month": 7}
    )
    assert audit.status_code == 200, audit.text
    assert audit.json()["status"] == expected["audit"]["status"]
    assert sum(transaction.is_locked for transaction in seeded.values() if transaction.date.month == 7) == expected["audit"]["locked_transaction_count"]
    aggregate = db_session.query(MonthlyAggregate).filter_by(month="2026-07").one()
    _assert_money(aggregate.total_income, expected["month"]["income"])
    _assert_money(aggregate.total_spend, expected["month"]["spend"])
    assert aggregate.transaction_count == expected["month"]["spending_count"]
    assert aggregate.is_finalized is True

    # AI can add commentary only. It cannot mutate any authoritative amount.
    before_ai = {
        "dashboard": {
            key: dashboard_data[key]
            for key in ("month_income", "month_spend", "savings_rate")
        },
        "cash_flow": {
            key: cash_flow.json()[key]
            for key in ("total_income", "total_spend", "net")
        },
        "report": {
            key: report_data[key]
            for key in ("total_income", "total_spend", "savings_rate")
        },
    }
    db_session.add(
        LLMConfiguration(
            provider="ollama_local",
            auth_method="none",
            model="golden-synthetic-model",
            base_url="http://127.0.0.1:11434",
            is_active=True,
        )
    )
    db_session.commit()
    monkeypatch.setattr("app.core.reporting.call_llm", lambda *_a, **_kw: _valid_llm_report())
    ai = auth_client.post(
        "/api/v1/reports/ai/insights",
        json={"month": fixture["month"], "consent": True},
    )
    assert ai.status_code == 200, ai.text
    assert ai.json()["insights"]["source"] == "llm"

    dashboard_after = auth_client.get(
        "/api/v1/dashboard/stats", params={"month": fixture["month"]}
    ).json()
    cash_flow_after = auth_client.get(
        "/api/v1/cash-flow/calendar", params={"month": fixture["month"]}
    ).json()
    report_after = auth_client.get(
        "/api/v1/reports/summary", params={"month": fixture["month"]}
    ).json()
    assert before_ai == {
        "dashboard": {
            key: dashboard_after[key]
            for key in ("month_income", "month_spend", "savings_rate")
        },
        "cash_flow": {
            key: cash_flow_after[key]
            for key in ("total_income", "total_spend", "net")
        },
        "report": {
            key: report_after[key]
            for key in ("total_income", "total_spend", "savings_rate")
        },
    }
