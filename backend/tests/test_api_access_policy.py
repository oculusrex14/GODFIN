import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "shared" / "api_access_policy.json"


def test_every_api_route_matches_the_reviewed_access_policy():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "verify_api_access_policy.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_route_policy_contains_paid_and_conditional_contracts():
    routes = json.loads(POLICY.read_text(encoding="utf-8"))["routes"]
    paid = {value["feature"] for value in routes.values() if value["access"] == "paid"}
    conditional = {
        value["feature"]
        for value in routes.values()
        if value["access"] == "conditional_paid"
    }

    assert paid == {
        "advanced_reports",
        "ai_classification",
        "behavior_insights",
        "multi_bank",
        "net_worth",
    }
    assert conditional == {"multi_bank"}
