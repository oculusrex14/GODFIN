from __future__ import annotations

import importlib.util
import shutil
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class ExtractionBenchmarkCase:
    fixture_id: str
    current_reconciled: bool
    candidate_reconciled: bool
    current_elapsed_ms: float
    candidate_elapsed_ms: float


def opendataloader_runtime_status() -> dict:
    java_path = shutil.which("java")
    package_available = importlib.util.find_spec("opendataloader_pdf") is not None
    return {
        "java_available": java_path is not None,
        "java_path": java_path,
        "package_available": package_available,
        "ready": java_path is not None and package_available,
        "shipped": False,
        "reason": (
            "Benchmark-only. GODFIN will not bundle Java until a redacted "
            "statement corpus proves a material reconciliation gain."
        ),
    }


def compare_extraction_results(
    cases: Iterable[ExtractionBenchmarkCase],
    *,
    minimum_gain: float = 0.05,
) -> dict:
    rows = list(cases)
    if not rows:
        return {
            "case_count": 0,
            "decision": "insufficient_evidence",
            "ship_candidate": False,
        }

    current_rate = sum(row.current_reconciled for row in rows) / len(rows)
    candidate_rate = sum(row.candidate_reconciled for row in rows) / len(rows)
    gain = candidate_rate - current_rate
    current_time = sum(row.current_elapsed_ms for row in rows) / len(rows)
    candidate_time = sum(row.candidate_elapsed_ms for row in rows) / len(rows)
    return {
        "case_count": len(rows),
        "current_reconciliation_rate": round(current_rate, 4),
        "candidate_reconciliation_rate": round(candidate_rate, 4),
        "reconciliation_gain": round(gain, 4),
        "current_mean_elapsed_ms": round(current_time, 2),
        "candidate_mean_elapsed_ms": round(candidate_time, 2),
        "decision": "ship" if gain >= minimum_gain else "retain_current",
        "ship_candidate": gain >= minimum_gain,
        "decisive_metric": "complete_reconciliation_without_manual_correction",
    }
