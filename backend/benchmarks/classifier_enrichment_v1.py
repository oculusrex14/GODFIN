"""Run the deterministic V1 enrichment safety benchmark on synthetic data."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
import time
import uuid
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.database import Base
from app.core.merchant_entity_service import find_merchant_candidates
from app.core.relationship_linker import suggest_transaction_relationships
from app.core.startup_migrations import apply_additive_schema_updates
from app.core.statement_parser import (
    StatementParseResult,
    StatementTransaction,
    _validate_savings_controls,
)
from app.core.transaction_enrichment import build_transaction_envelope
from app.models.account import Account
from app.models.transaction import Transaction
from app.seed import run_seeds


FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "tests"
    / "fixtures"
    / "classifier_enrichment_v1.json"
)


def _baseline_semantic(coarse: str) -> str:
    return {
        "income": "other_income",
        "refund": "refund",
        "reversal": "reversal",
        "cashback": "cashback_reward",
        "internal_transfer": "internal_transfer",
    }.get(coarse, "unknown")


def _macro_f1(expected: list[str], predicted: list[str]) -> float:
    labels = sorted(set(expected) | set(predicted))
    if not labels:
        return 1.0
    scores = []
    for label in labels:
        true_positive = sum(
            1 for actual, guess in zip(expected, predicted) if actual == guess == label
        )
        false_positive = sum(
            1 for actual, guess in zip(expected, predicted) if actual != label and guess == label
        )
        false_negative = sum(
            1 for actual, guess in zip(expected, predicted) if actual == label and guess != label
        )
        precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0
        recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0
        scores.append(2 * precision * recall / (precision + recall) if precision + recall else 0)
    return sum(scores) / len(scores)


def _transaction(
    session,
    *,
    account_id: str,
    when: date,
    amount: float,
    direction: str,
    merchant: str,
    source: str,
    detail: str,
    reference: str | None = None,
) -> Transaction:
    row = Transaction(
        id=str(uuid.uuid4()),
        date=when,
        raw_text=merchant,
        merchant_raw=merchant,
        merchant_normalized=merchant.upper(),
        amount=amount,
        type=direction,
        instrument="bank",
        account_id=account_id,
        source=source,
        status="settled",
        semantic_type="unknown",
        semantic_detail=detail,
        reference_number=reference,
    )
    session.add(row)
    session.flush()
    return row


def _relationship_metrics(session) -> tuple[float, float]:
    accounts = session.query(Account).limit(2).all()
    purchase = _transaction(
        session,
        account_id=accounts[0].id,
        when=date(2026, 8, 1),
        amount=411.11,
        direction="debit",
        merchant="SYNTHETIC SHOP",
        source="statement_upload",
        detail="purchase",
        reference="RELREFUND001",
    )
    refund = _transaction(
        session,
        account_id=accounts[0].id,
        when=date(2026, 8, 3),
        amount=411.11,
        direction="credit",
        merchant="SYNTHETIC SHOP REFUND",
        source="gmail",
        detail="refund",
        reference="RELREFUND001",
    )
    transfer_out = _transaction(
        session,
        account_id=accounts[0].id,
        when=date(2026, 8, 5),
        amount=522.22,
        direction="debit",
        merchant="OWN ACCOUNT",
        source="statement_upload",
        detail="transfer_out",
        reference="RELTRANSFER01",
    )
    transfer_in = _transaction(
        session,
        account_id=accounts[1].id,
        when=date(2026, 8, 5),
        amount=522.22,
        direction="credit",
        merchant="OWN ACCOUNT",
        source="statement_upload",
        detail="transfer_in",
        reference="RELTRANSFER01",
    )
    _transaction(
        session,
        account_id=accounts[0].id,
        when=date(2026, 8, 7),
        amount=633.33,
        direction="debit",
        merchant="UNRELATED ALPHA",
        source="statement_upload",
        detail="unknown",
    )
    _transaction(
        session,
        account_id=accounts[1].id,
        when=date(2026, 8, 7),
        amount=633.33,
        direction="credit",
        merchant="UNRELATED OMEGA",
        source="statement_upload",
        detail="unknown",
    )
    session.commit()

    expected = {
        (refund.id, purchase.id, "refund_of"),
        (transfer_out.id, transfer_in.id, "internal_transfer_pair"),
    }
    actual = {
        (item.from_transaction_id, item.to_transaction_id, item.relationship_type)
        for item in suggest_transaction_relationships(session)
    }
    true_positive = len(expected & actual)
    precision = true_positive / len(actual) if actual else 0.0
    recall = true_positive / len(expected) if expected else 1.0
    session.rollback()
    return precision, recall


def _balance_control_accuracy() -> float:
    cases = (
        (
            True,
            StatementParseResult(
                transactions=[
                    StatementTransaction(date=date(2026, 8, 1), description="A", amount=100, txn_type="credit", closing_balance=1100),
                    StatementTransaction(date=date(2026, 8, 2), description="B", amount=50, txn_type="debit", closing_balance=1050),
                ]
            ),
        ),
        (
            False,
            StatementParseResult(
                transactions=[
                    StatementTransaction(date=date(2026, 8, 1), description="A", amount=100, txn_type="credit", closing_balance=1100),
                    StatementTransaction(date=date(2026, 8, 2), description="B", amount=50, txn_type="debit", closing_balance=999),
                ]
            ),
        ),
    )
    correct = 0
    for expected_pass, result in cases:
        _validate_savings_controls(result)
        correct += (result.reconciliation_status == "passed") == expected_pass
    return correct / len(cases)


def run_benchmark() -> dict[str, object]:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    cases = fixture["cases"]
    with tempfile.TemporaryDirectory(prefix="godfin-classifier-benchmark-") as temp_dir:
        db_path = Path(temp_dir) / "benchmark.db"
        engine = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(engine)
        apply_additive_schema_updates(str(db_path))
        Session = sessionmaker(bind=engine)
        query_counter = Counter()

        @event.listens_for(engine, "before_cursor_execute")
        def count_queries(*_args):
            query_counter["count"] += 1

        with Session() as session:
            run_seeds(session)
            query_counter.clear()
            semantic_correct = 0
            baseline_correct = 0
            predicted_non_unknown = 0
            correct_non_unknown = 0
            expected_unknown = 0
            correct_abstentions = 0
            auto_total = 0
            auto_correct = 0
            category_expected: list[str] = []
            category_predicted: list[str] = []
            latencies_ms: list[float] = []
            partitions = defaultdict(int)

            for case in cases:
                partitions[case["partition"]] += 1
                started = time.perf_counter()
                envelope = build_transaction_envelope(
                    raw_text=case["raw_text"],
                    source_type="benchmark",
                    source_account_id="synthetic",
                    booking_date=date(2026, 8, 1),
                    amount="100.00",
                    direction=case["direction"],
                    instrument=case.get("instrument"),
                    merchant_raw=case.get("merchant_raw"),
                    coarse_semantic=case.get("coarse_semantic", "unknown"),
                    category=case.get("category"),
                    subcategory=case.get("subcategory"),
                    parser_version="benchmark-v1",
                )
                candidates = find_merchant_candidates(
                    session,
                    envelope.merchant_candidate or case.get("merchant_raw") or case["raw_text"],
                    vpa=envelope.vpa,
                )
                latencies_ms.append((time.perf_counter() - started) * 1000)

                expected_semantic = case["expected_semantic"]
                semantic_correct += envelope.semantic_detail == expected_semantic
                baseline_correct += _baseline_semantic(case.get("coarse_semantic", "unknown")) == expected_semantic
                if envelope.semantic_detail != "unknown":
                    predicted_non_unknown += 1
                    correct_non_unknown += envelope.semantic_detail == expected_semantic
                if expected_semantic == "unknown":
                    expected_unknown += 1
                    correct_abstentions += envelope.semantic_detail == "unknown"
                if "expected_processor" in case:
                    semantic_correct += envelope.processor_candidate == case["expected_processor"]
                if "expected_vpa_role" in case:
                    semantic_correct += envelope.vpa_role == case["expected_vpa_role"]

                auto = next((candidate for candidate in candidates if candidate.is_auto_acceptable), None)
                if auto:
                    auto_total += 1
                    auto_correct += auto.canonical_name == case.get("expected_merchant")
                if case.get("category") and case.get("expected_merchant"):
                    category_expected.append(case["category"])
                    category_predicted.append(
                        (auto.category or "UNKNOWN") if auto else "UNKNOWN"
                    )

            relationship_precision, relationship_recall = _relationship_metrics(session)
        engine.dispose()

    semantic_checks = len(cases) + sum(
        int("expected_processor" in case) + int("expected_vpa_role" in case)
        for case in cases
    )
    latency_p95 = statistics.quantiles(latencies_ms, n=20)[18]
    metrics = {
        "fixture_schema_version": fixture["schema_version"],
        "case_count": len(cases),
        "partition_count": len(partitions),
        "semantic_accuracy": semantic_correct / semantic_checks,
        "baseline_semantic_accuracy": baseline_correct / len(cases),
        "safety_precision": correct_non_unknown / predicted_non_unknown,
        "unknown_abstention_accuracy": correct_abstentions / expected_unknown,
        "merchant_auto_precision": auto_correct / auto_total if auto_total else 1.0,
        "merchant_auto_coverage": auto_total / len(cases),
        "category_macro_f1": _macro_f1(category_expected, category_predicted),
        "relationship_precision": relationship_precision,
        "relationship_recall": relationship_recall,
        "balance_control_accuracy": _balance_control_accuracy(),
        "latency_p95_ms": latency_p95,
        "query_count": query_counter["count"],
    }
    metrics["passed"] = bool(
        metrics["semantic_accuracy"] >= 0.95
        and metrics["semantic_accuracy"] > metrics["baseline_semantic_accuracy"]
        and metrics["safety_precision"] >= 0.98
        and metrics["unknown_abstention_accuracy"] >= 0.95
        and metrics["merchant_auto_precision"] == 1.0
        and metrics["relationship_precision"] == 1.0
        and metrics["relationship_recall"] == 1.0
        and metrics["balance_control_accuracy"] == 1.0
        and metrics["latency_p95_ms"] < 25
    )
    return metrics


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    metrics = run_benchmark()
    if args.json:
        print(json.dumps(metrics, indent=2, sort_keys=True))
    else:
        for key, value in metrics.items():
            print(f"{key}: {value}")
    return 0 if metrics["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
