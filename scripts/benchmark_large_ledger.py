#!/usr/bin/env python3
"""Benchmark read-only GODFIN paths against isolated synthetic SQLite ledgers.

The script never opens the configured GODFIN database. Each requested size is
created in a temporary directory, populated with deterministic synthetic rows,
measured, and deleted before exit.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import resource
import sys
import tempfile
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from time import perf_counter

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.api.v1.endpoints.dashboard import dashboard_stats  # noqa: E402
from app.core.behavior_insights import compute_behavior_insights  # noqa: E402
from app.core.database import Base  # noqa: E402
from app.core.reporting import prepare_summary_report  # noqa: E402
from app.models import *  # noqa: E402,F401,F403
from app.models.transaction import Transaction  # noqa: E402
from app.seed import SAVINGS_ACCOUNT_ID, run_seeds  # noqa: E402


@contextmanager
def select_counter(engine):
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


def max_rss_mib() -> float:
    value = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    # macOS reports bytes; Linux reports KiB.
    divisor = 1024 * 1024 if sys.platform == "darwin" else 1024
    return round(value / divisor, 1)


def synthetic_transaction(index: int) -> Transaction:
    is_income = index % 5 == 0
    merchant = (
        f"SYNTHETIC EMPLOYER {index % 8}"
        if is_income
        else f"SYNTHETIC MERCHANT {index % 500}"
    )
    return Transaction(
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
        source="synthetic_benchmark",
        is_income=is_income,
        semantic_type="income" if is_income else "expense",
    )


def seed_ledger(session, rows: int) -> float:
    started = perf_counter()
    for batch_start in range(0, rows, 5_000):
        batch_end = min(rows, batch_start + 5_000)
        session.bulk_save_objects(
            [
                synthetic_transaction(index)
                for index in range(batch_start, batch_end)
            ]
        )
        session.commit()
        session.expunge_all()
    return round(perf_counter() - started, 3)


def measure(session, engine, name: str, operation) -> dict:
    session.expire_all()
    with select_counter(engine) as selected:
        started = perf_counter()
        result = operation()
        elapsed_ms = round((perf_counter() - started) * 1000, 2)
        selects = selected()
    if result is None:
        raise RuntimeError(f"Synthetic {name} benchmark returned no result")
    return {
        "elapsed_ms": elapsed_ms,
        "select_statements": selects,
    }


def benchmark_size(rows: int) -> dict:
    with tempfile.TemporaryDirectory(prefix="godfin-synthetic-ledger-") as directory:
        db_path = Path(directory) / "benchmark.db"
        engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine)
        session = Session()
        try:
            run_seeds(session)
            seed_seconds = seed_ledger(session, rows)
            operations = {
                "dashboard": measure(
                    session,
                    engine,
                    "dashboard",
                    lambda: dashboard_stats(
                        month="2026-07",
                        period="full",
                        db=session,
                        _user=True,
                    ),
                ),
                "report_summary": measure(
                    session,
                    engine,
                    "report_summary",
                    lambda: prepare_summary_report(
                        session,
                        "2026-07",
                        as_of=date(2026, 8, 1),
                    ),
                ),
                "behavior_insights": measure(
                    session,
                    engine,
                    "behavior_insights",
                    lambda: compute_behavior_insights(
                        session,
                        today=date(2026, 8, 1),
                    ),
                ),
            }
            return {
                "rows": rows,
                "database_mib": round(db_path.stat().st_size / (1024 * 1024), 2),
                "seed_seconds": seed_seconds,
                "process_max_rss_mib": max_rss_mib(),
                "operations": operations,
            }
        finally:
            session.close()
            engine.dispose()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--sizes",
        nargs="+",
        type=int,
        default=[10_000, 50_000, 100_000],
    )
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    sizes = sorted(set(args.sizes))
    if not sizes or any(size < 1 or size > 1_000_000 for size in sizes):
        raise SystemExit("Benchmark sizes must be between 1 and 1,000,000 rows")
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "fixture": "deterministic_synthetic_financial_ledger",
        "live_database_accessed": False,
        "environment": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "logical_cpu_count": os.cpu_count(),
        },
        "results": [benchmark_size(size) for size in sizes],
    }
    encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output:
        output = args.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
