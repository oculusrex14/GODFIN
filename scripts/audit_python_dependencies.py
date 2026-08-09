#!/usr/bin/env python3
"""Run GODFIN's Python dependency audit with one fail-closed exception.

cryptography 49.0.0 is affected by PYSEC-2026-3552 only when an application
decrypts attacker-controlled PKCS#7 EnvelopedData. GODFIN does not implement
PKCS#7/S/MIME decryption. The upstream fix is assigned to 50.0.0, which is not
yet available on PyPI. This wrapper keeps every other pip-audit finding fatal,
rejects the exception if the locked version changes, and rejects it if an
affected API is introduced into runtime source.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / "backend" / "requirements-lock.txt"
RUNTIME_SOURCE = ROOT / "backend" / "app"
TEMPORARILY_ACCEPTED_VERSION = "49.0.0"
TEMPORARILY_ACCEPTED_ADVISORY = "PYSEC-2026-3552"
AFFECTED_APIS = (
    "pkcs7_decrypt_der",
    "pkcs7_decrypt_pem",
    "pkcs7_decrypt_smime",
)


def _locked_cryptography_version() -> str:
    lock_text = LOCK_PATH.read_text(encoding="utf-8")
    match = re.search(r"^cryptography==([^ \\\n]+)", lock_text, flags=re.MULTILINE)
    if match is None:
        raise RuntimeError("cryptography is not pinned in the runtime lock")
    return match.group(1)


def _affected_runtime_uses() -> list[str]:
    findings: list[str] = []
    for source_path in sorted(RUNTIME_SOURCE.rglob("*.py")):
        source_text = source_path.read_text(encoding="utf-8")
        for api_name in AFFECTED_APIS:
            if api_name in source_text:
                try:
                    display_path = source_path.relative_to(ROOT)
                except ValueError:
                    display_path = source_path
                findings.append(f"{display_path}: {api_name}")
    return findings


def main() -> int:
    locked_version = _locked_cryptography_version()
    if locked_version != TEMPORARILY_ACCEPTED_VERSION:
        print(
            "The temporary cryptography advisory exception is stale: "
            f"expected {TEMPORARILY_ACCEPTED_VERSION}, found {locked_version}. "
            "Remove or reassess the exception before continuing.",
            file=sys.stderr,
        )
        return 1

    affected_uses = _affected_runtime_uses()
    if affected_uses:
        print(
            "The temporarily excepted PKCS#7 APIs now appear in GODFIN runtime "
            "source; PYSEC-2026-3552 must not be ignored:",
            file=sys.stderr,
        )
        for finding in affected_uses:
            print(f"- {finding}", file=sys.stderr)
        return 1

    print(
        "Temporary exception: PYSEC-2026-3552 for cryptography 49.0.0. "
        "GODFIN runtime source does not use the affected PKCS#7 decrypt APIs; "
        "all other advisories remain fatal."
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip_audit",
            "-r",
            str(LOCK_PATH),
            "--ignore-vuln",
            TEMPORARILY_ACCEPTED_ADVISORY,
        ],
        cwd=ROOT,
        check=False,
    )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
