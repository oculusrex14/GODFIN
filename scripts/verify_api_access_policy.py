#!/usr/bin/env python3
"""Verify the complete FastAPI route-access and paid-feature policy snapshot."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
POLICY_PATH = ROOT / "shared" / "api_access_policy.json"

sys.path.insert(0, str(BACKEND))
os.environ.setdefault("GODFIN_TESTING", "1")

from app.api.v1.entitlements import (  # noqa: E402
    CONDITIONAL_ENTITLEMENT_MARKER,
    ENTITLEMENT_MARKER,
)
from app.core.auth import get_current_user  # noqa: E402
from app.core.entitlements import entitlement_manifest  # noqa: E402
from app.main import app  # noqa: E402


def _walk_dependencies(dependant: Any) -> Iterable[Any]:
    yield dependant
    for dependency in dependant.dependencies:
        yield from _walk_dependencies(dependency)


def _effective_routes() -> Iterable[Any]:
    for route in app.routes:
        contexts = getattr(route, "effective_route_contexts", None)
        if callable(contexts):
            yield from contexts()
        elif hasattr(route, "dependant") and hasattr(route, "path"):
            yield route


def _route_key(method: str, path: str) -> str:
    return f"{method.upper()} {path}"


def current_policy() -> dict[str, Any]:
    routes: dict[str, dict[str, str]] = {}
    released_features = {
        name
        for name, definition in entitlement_manifest()["features"].items()
        if definition.get("status") == "released"
    }

    for route in _effective_routes():
        dependencies = list(_walk_dependencies(route.dependant))
        calls = {dependency.call for dependency in dependencies}
        paid_features = {
            getattr(dependency.call, ENTITLEMENT_MARKER)
            for dependency in dependencies
            if getattr(dependency.call, ENTITLEMENT_MARKER, None)
        }
        conditional_feature = getattr(
            route.endpoint,
            CONDITIONAL_ENTITLEMENT_MARKER,
            None,
        )
        authenticated = get_current_user in calls

        if paid_features and conditional_feature:
            raise AssertionError(
                f"{route.path} declares both unconditional and conditional paid access"
            )
        if len(paid_features) > 1:
            raise AssertionError(
                f"{route.path} declares multiple paid features: {sorted(paid_features)}"
            )

        if paid_features:
            feature = paid_features.pop()
            if not authenticated:
                raise AssertionError(f"Paid route {route.path} is not authenticated")
            if feature not in released_features:
                raise AssertionError(
                    f"Paid route {route.path} uses unreleased feature {feature}"
                )
            access = {"access": "paid", "feature": feature}
        elif conditional_feature:
            if not authenticated:
                raise AssertionError(
                    f"Conditional paid route {route.path} is not authenticated"
                )
            if conditional_feature not in released_features:
                raise AssertionError(
                    f"Conditional route {route.path} uses unreleased feature "
                    f"{conditional_feature}"
                )
            access = {
                "access": "conditional_paid",
                "feature": conditional_feature,
            }
        elif authenticated:
            access = {"access": "authenticated_free"}
        else:
            access = {"access": "public"}

        for method in sorted(route.methods):
            key = _route_key(method, route.path)
            if key in routes:
                raise AssertionError(f"Duplicate API route policy key: {key}")
            routes[key] = access

    return {
        "schema_version": 1,
        "default": "deny_unclassified",
        "routes": dict(sorted(routes.items())),
    }


def verify_policy() -> None:
    expected = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    actual = current_policy()
    if expected == actual:
        return

    expected_routes = expected.get("routes", {})
    actual_routes = actual["routes"]
    missing = sorted(set(expected_routes) - set(actual_routes))
    added = sorted(set(actual_routes) - set(expected_routes))
    changed = sorted(
        key
        for key in set(expected_routes) & set(actual_routes)
        if expected_routes[key] != actual_routes[key]
    )
    details = []
    if missing:
        details.append(f"removed routes: {missing}")
    if added:
        details.append(f"unclassified new routes: {added}")
    if changed:
        details.append(
            "access changes: "
            + str(
                {
                    key: {
                        "expected": expected_routes[key],
                        "actual": actual_routes[key],
                    }
                    for key in changed
                }
            )
        )
    raise AssertionError(
        "API access policy changed without an explicit reviewed snapshot update; "
        + "; ".join(details)
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--write",
        action="store_true",
        help="Deliberately replace the reviewed route snapshot.",
    )
    args = parser.parse_args()
    if args.write:
        POLICY_PATH.write_text(
            json.dumps(current_policy(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"Wrote {POLICY_PATH.relative_to(ROOT)}")
    else:
        verify_policy()
        print("API access policy is complete and unchanged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
