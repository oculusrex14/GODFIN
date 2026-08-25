from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_documentation_contracts_match_repository_sources():
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/verify_documentation_contracts.py"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
