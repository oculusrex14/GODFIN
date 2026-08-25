#!/usr/bin/env python3
"""Verify one private statement without printing its financial contents."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.parsers import parse_registered_statement  # noqa: E402
from app.core.statement_file_safety import validate_statement_file  # noqa: E402


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run GODFIN's fail-closed parser against a private PDF and emit "
            "only a digest and pass/fail metadata."
        ),
    )
    parser.add_argument("path", type=Path)
    parser.add_argument("--expected-profile", required=True)
    parser.add_argument("--expected-count", required=True, type=int)
    parser.add_argument("--account-last4")
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    contents = args.path.read_bytes()
    validate_statement_file(contents, "pdf")
    result = parse_registered_statement(
        contents,
        "pdf",
        account_last4=args.account_last4,
    )
    checks = {
        "profile": result.parser_profile == args.expected_profile,
        "recognized": result.recognized,
        "reconciled": result.reconciliation_status == "passed",
        "exact_transaction_count": len(result.transactions) == args.expected_count,
        "period_present": bool(result.period_start and result.period_end),
        "account_identity_present": bool(result.account_last4),
        "no_parser_errors": not result.errors,
    }
    passed = all(checks.values())
    print(
        json.dumps(
            {
                "sha256": hashlib.sha256(contents).hexdigest(),
                "expected_profile": args.expected_profile,
                "expected_count": args.expected_count,
                "checks": checks,
                "passed": passed,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
