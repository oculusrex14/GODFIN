#!/usr/bin/env python3
"""Audit every locked Python surface without vulnerability exceptions."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCK_PATHS = (
    ROOT / "backend" / "requirements-lock.txt",
    ROOT / "backend" / "requirements-test-lock.txt",
    ROOT / "backend" / "requirements-build-lock.txt",
)
def main() -> int:
    for lock_path in LOCK_PATHS:
        print(f"Auditing {lock_path.relative_to(ROOT)}")
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "pip_audit",
                "-r",
                str(lock_path),
            ],
            cwd=ROOT,
            check=False,
        )
        if completed.returncode != 0:
            return completed.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
