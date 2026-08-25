#!/usr/bin/env python3
"""Fail CI when the risk-oriented test inventory or runtime contract drifts."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATRIX_PATH = ROOT / "docs" / "production-remediation" / "TEST_RISK_MATRIX.json"
REGISTER_PATH = (
    ROOT
    / "docs"
    / "production-remediation"
    / "REMEDIATION_FINDINGS_REGISTER.csv"
)
CI_PATH = ROOT / ".github" / "workflows" / "ci.yml"
REQUIRED_DOMAINS = {
    "authorization_and_entitlements",
    "destructive_and_recovery_operations",
    "financial_money_and_reports",
    "idempotency_concurrency_and_jobs",
    "integration_failure_boundaries",
    "parser_and_import_controls",
    "schema_startup_and_migrations",
    "user_interface_and_accessibility",
}


def verify() -> None:
    matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    if matrix.get("schema_version") != 1:
        raise AssertionError("Unsupported test-risk matrix schema")
    if matrix.get("runtime_contract", {}).get("python") != "3.12":
        raise AssertionError("The backend test runtime must remain Python 3.12")
    if matrix.get("runtime_contract", {}).get("node") != "22":
        raise AssertionError("Production Node builds must remain locked to Node 22")

    domains = matrix.get("risk_domains", {})
    missing_domains = REQUIRED_DOMAINS - set(domains)
    if missing_domains:
        raise AssertionError(f"Missing test risk domains: {sorted(missing_domains)}")

    missing_files: list[str] = []
    empty_invariants: list[str] = []
    for domain, definition in domains.items():
        tests = definition.get("tests", [])
        invariants = definition.get("invariants", [])
        if not tests or not invariants:
            empty_invariants.append(domain)
        for relative in tests:
            if not (ROOT / relative).is_file():
                missing_files.append(relative)
    if missing_files:
        raise AssertionError(f"Missing risk-matrix tests: {sorted(missing_files)}")
    if empty_invariants:
        raise AssertionError(
            f"Risk domains without tests or invariants: {sorted(empty_invariants)}"
        )

    mutation_domains = {
        target.get("domain") for target in matrix.get("selective_mutation_targets", [])
    }
    if mutation_domains != {"authorization", "financial formulas"}:
        raise AssertionError("Authorization and financial formula mutation targets are required")

    with REGISTER_PATH.open(newline="", encoding="utf-8") as register_file:
        rows = list(csv.DictReader(register_file))
    missing_test_evidence = [
        row["Finding ID"]
        for row in rows
        if row["Validated severity"] in {"Critical", "High"}
        and row["Status"] in {"Verified", "Partially verified"}
        and not row["Tests added"].strip()
    ]
    if missing_test_evidence:
        raise AssertionError(
            "Verified high-risk findings lack test evidence: "
            + ", ".join(missing_test_evidence)
        )

    ci = CI_PATH.read_text(encoding="utf-8")
    for required in (
        'python-version: "3.12"',
        'node-version: "22"',
        "python scripts/verify_api_access_policy.py",
        "python scripts/verify_test_governance.py",
        "python -m pytest backend/tests -q",
    ):
        if required not in ci:
            raise AssertionError(f"CI is missing locked test contract: {required}")


def main() -> int:
    verify()
    print("Risk-oriented test governance is complete and consistent.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, OSError, ValueError, csv.Error) as exc:
        print(f"Test governance verification failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
