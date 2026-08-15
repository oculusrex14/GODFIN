#!/usr/bin/env python3
"""Verify generated supply-chain evidence and public-promotion clearance."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SBOM_PATH = ROOT / "sbom" / "godfin.cdx.json"
CLEARANCE_PATH = ROOT / "supply-chain" / "legal-clearance.json"


def _run_generation_check() -> None:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "generate_supply_chain_artifacts.py"), "--check"],
        cwd=ROOT,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError("generated SBOM or notices are stale")


def _verify_sbom(path: Path) -> tuple[str, str]:
    sbom_bytes = path.read_bytes()
    sbom = json.loads(sbom_bytes)
    if sbom.get("bomFormat") != "CycloneDX" or sbom.get("specVersion") != "1.6":
        raise RuntimeError("SBOM is not CycloneDX 1.6")
    components = sbom.get("components", [])
    if not components:
        raise RuntimeError("SBOM contains no components")
    purls = [item.get("purl") for item in components]
    if None in purls or len(purls) != len(set(purls)):
        raise RuntimeError("SBOM purls are missing or duplicated")
    for component in components:
        expressions = [item.get("expression") for item in component.get("licenses", [])]
        if not expressions or any(not value or value == "NOASSERTION" for value in expressions):
            raise RuntimeError(f"unresolved SBOM license for {component.get('purl')}")
    root_component = sbom.get("metadata", {}).get("component", {})
    return hashlib.sha256(sbom_bytes).hexdigest(), str(root_component.get("version", ""))


def _verify_clearance(
    path: Path, sbom_hash: str, version: str, *, promotion: bool
) -> None:
    clearance = json.loads(path.read_text(encoding="utf-8"))
    if clearance.get("schema_version") != 1:
        raise RuntimeError("unsupported legal-clearance schema")
    status = clearance.get("status")
    if status not in {"pending", "approved", "rejected"}:
        raise RuntimeError("legal-clearance status must be pending, approved, or rejected")
    if not promotion:
        return
    if status != "approved":
        raise RuntimeError("public promotion blocked: qualified legal clearance is not approved")
    if clearance.get("reviewed_sbom_sha256") != sbom_hash:
        raise RuntimeError("public promotion blocked: legal clearance does not match the exact SBOM")
    if clearance.get("reviewed_release") != version:
        raise RuntimeError("public promotion blocked: legal clearance does not match the release version")
    if not clearance.get("reviewed_by") or not clearance.get("reviewed_at"):
        raise RuntimeError("public promotion blocked: legal review evidence is incomplete")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--promotion", action="store_true", help="require exact approved legal clearance")
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        help="verify the archived release copies instead of checked-in generated files",
    )
    args = parser.parse_args()
    try:
        if args.artifact_dir:
            artifact_dir = args.artifact_dir.resolve()
            required = {
                "LICENSE",
                "THIRD_PARTY_NOTICES.md",
                "godfin.cdx.json",
                "legal-clearance.json",
            }
            missing = sorted(name for name in required if not (artifact_dir / name).is_file())
            if missing:
                raise RuntimeError(f"release evidence is missing: {', '.join(missing)}")
            sbom_path = artifact_dir / "godfin.cdx.json"
            clearance_path = artifact_dir / "legal-clearance.json"
        else:
            _run_generation_check()
            sbom_path = SBOM_PATH
            clearance_path = CLEARANCE_PATH
        sbom_hash, version = _verify_sbom(sbom_path)
        _verify_clearance(
            clearance_path, sbom_hash, version, promotion=args.promotion
        )
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"Supply-chain verification failed: {exc}", file=sys.stderr)
        return 1
    mode = "public-promotion" if args.promotion else "private-draft"
    print(f"Supply-chain evidence verified for {mode}; SBOM SHA-256 {sbom_hash}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
