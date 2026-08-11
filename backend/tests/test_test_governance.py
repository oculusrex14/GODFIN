import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_risk_oriented_test_governance_contract():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "verify_test_governance.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
