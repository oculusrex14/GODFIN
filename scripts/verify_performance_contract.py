#!/usr/bin/env python3
"""Verify that every performance budget is valid and has an enforced consumer."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUDGET_PATH = ROOT / "performance" / "budgets.json"
ALLOWED_UNITS = {"milliseconds", "mebibytes", "select_statements"}


def main() -> int:
    payload = json.loads(BUDGET_PATH.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 2:
        raise SystemExit("performance/budgets.json must use schema_version 2")
    margin = payload.get("regression_margin")
    if not isinstance(margin, (int, float)) or not 0 < margin <= 0.25:
        raise SystemExit("regression_margin must be greater than 0 and at most 0.25")

    budgets = payload.get("budgets")
    if not isinstance(budgets, dict) or not budgets:
        raise SystemExit("At least one performance budget is required")

    errors: list[str] = []
    for name, budget in sorted(budgets.items()):
        if not isinstance(budget, dict):
            errors.append(f"{name}: budget must be an object")
            continue
        baseline = budget.get("accepted_baseline")
        maximum = budget.get("absolute_max")
        if not isinstance(baseline, (int, float)) or baseline <= 0:
            errors.append(f"{name}: accepted_baseline must be positive")
        if not isinstance(maximum, (int, float)) or maximum <= 0:
            errors.append(f"{name}: absolute_max must be positive")
        if (
            isinstance(baseline, (int, float))
            and isinstance(maximum, (int, float))
            and baseline > maximum
        ):
            errors.append(f"{name}: baseline cannot exceed absolute maximum")
        if budget.get("unit") not in ALLOWED_UNITS:
            errors.append(f"{name}: unsupported or missing unit")

        consumer = budget.get("consumer")
        if not isinstance(consumer, str) or not consumer:
            errors.append(f"{name}: consumer is required")
            continue
        consumer_path = (ROOT / consumer).resolve()
        try:
            consumer_path.relative_to(ROOT.resolve())
        except ValueError:
            errors.append(f"{name}: consumer escapes the repository")
            continue
        if not consumer_path.is_file():
            errors.append(f"{name}: consumer does not exist: {consumer}")
            continue
        if name not in consumer_path.read_text(encoding="utf-8"):
            errors.append(f"{name}: consumer does not reference this budget")

    if errors:
        raise SystemExit("\n".join(errors))
    print(f"Performance contract verified: {len(budgets)} enforced budgets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
