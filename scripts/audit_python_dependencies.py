#!/usr/bin/env python3
"""Audit every locked Python surface with one fail-closed exception.

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
LOCK_PATHS = (
    ROOT / "backend" / "requirements-lock.txt",
    ROOT / "backend" / "requirements-test-lock.txt",
    ROOT / "backend" / "requirements-build-lock.txt",
)
RUNTIME_SOURCE = ROOT / "backend" / "app"
TEMPORARILY_ACCEPTED_VERSION = "49.0.0"
TEMPORARILY_ACCEPTED_ADVISORY = "PYSEC-2026-3552"
AFFECTED_APIS = (
    "pkcs7_decrypt_der",
    "pkcs7_decrypt_pem",
    "pkcs7_decrypt_smime",
)


def _locked_cryptography_versions() -> dict[Path, str]:
    versions: dict[Path, str] = {}
    for lock_path in LOCK_PATHS:
        lock_text = lock_path.read_text(encoding="utf-8")
        match = re.search(
            r"^cryptography==([^ \\\n]+)", lock_text, flags=re.MULTILINE
        )
        if match is None:
            raise RuntimeError(f"cryptography is not pinned in {lock_path.name}")
        versions[lock_path] = match.group(1)
    return versions


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
    locked_versions = _locked_cryptography_versions()
    stale_versions = {
        lock_path.name: version
        for lock_path, version in locked_versions.items()
        if version != TEMPORARILY_ACCEPTED_VERSION
    }
    if stale_versions:
        print(
            "The temporary cryptography advisory exception is stale: "
            f"expected {TEMPORARILY_ACCEPTED_VERSION}, found {stale_versions}. "
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
    for lock_path in LOCK_PATHS:
        print(f"Auditing {lock_path.relative_to(ROOT)}")
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "pip_audit",
                "-r",
                str(lock_path),
                "--ignore-vuln",
                TEMPORARILY_ACCEPTED_ADVISORY,
            ],
            cwd=ROOT,
            check=False,
        )
        if completed.returncode != 0:
            return completed.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
