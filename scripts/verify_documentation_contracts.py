#!/usr/bin/env python3
"""Fail when active GODFIN documentation contradicts repository contracts."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_BANNER = "ARCHIVED HISTORICAL DOCUMENT"
LEGACY_DOCUMENTS = (
    "Claude_Build_Plan.md",
    "GODFIN_Final_Build_Specification_v1 .md",
    "change_summary/FINAL_CHANGE_SUMMARY.md",
    "change_summary/change_log.md",
    "tools_used.md",
    "docs/ui-glass-tracking/changelog.md",
)
ADR_FILES = tuple(
    f"docs/architecture/{number:04d}-{name}.md"
    for number, name in (
        (1, "local-app-cloud-boundary"),
        (2, "exact-money-and-sqlite"),
        (3, "schema-lifecycle"),
        (4, "oauth-boundaries"),
        (5, "lifetime-licensing"),
        (6, "private-release-promotion"),
    )
)


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _missing_local_links(path: str) -> list[str]:
    source = ROOT / path
    missing: list[str] = []
    for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", _read(path)):
        clean = target.strip().strip("<>").split("#", 1)[0]
        if not clean or clean.startswith(("http://", "https://", "mailto:")):
            continue
        if not (source.parent / clean).resolve().exists():
            missing.append(target)
    return missing


def verify() -> list[str]:
    errors: list[str] = []
    generated = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/generate_documentation_facts.py"),
            "--check",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if generated.returncode:
        errors.append(generated.stderr.strip() or "Generated stack facts are stale")

    required_links = {
        "README.md": (
            "docs/ENGINEERING_GUIDE.md",
            "docs/generated/STACK_FACTS.md",
            "PLAN.md",
        ),
        "CLAUDE.md": ("docs/ENGINEERING_GUIDE.md",),
        "desktop/README.md": ("../docs/ENGINEERING_GUIDE.md",),
        "frontend/README.md": ("../docs/ENGINEERING_GUIDE.md",),
        "website/README.md": ("../docs/ENGINEERING_GUIDE.md",),
        "docs/ENGINEERING_GUIDE.md": (
            "generated/STACK_FACTS.md",
            "DATABASE_LIFECYCLE.md",
            "PRODUCTION_RELEASE.md",
        ),
    }
    for path, links in required_links.items():
        text = _read(path)
        for link in links:
            if link not in text:
                errors.append(f"{path} must link to {link}")

    linked_docs = (
        "README.md",
        "docs/ENGINEERING_GUIDE.md",
        "docs/architecture/README.md",
        "desktop/README.md",
        "frontend/README.md",
        "website/README.md",
    )
    for path in linked_docs:
        for target in _missing_local_links(path):
            errors.append(f"{path} has a missing local link: {target}")

    for path in LEGACY_DOCUMENTS:
        first_lines = "\n".join(_read(path).splitlines()[:8])
        if ARCHIVE_BANNER not in first_lines:
            errors.append(f"{path} lacks the required archive banner")

    for path in ADR_FILES:
        text = _read(path)
        if "Status: Accepted" not in text:
            errors.append(f"{path} is missing accepted status")

    claude = _read("CLAUDE.md")
    prohibited_claude = {
        "Single source of truth for project requirements": "legacy build specification authority",
        "persistent token storage": "obsolete renderer token persistence",
        "Use Alembic": "unsupported Alembic instruction",
        "--host 0.0.0.0": "unsafe default bind instruction",
    }
    for phrase, description in prohibited_claude.items():
        if phrase.lower() in claude.lower():
            errors.append(f"CLAUDE.md contains {description}: {phrase}")

    active_setup_docs = (
        "README.md",
        "CLAUDE.md",
        "docs/ENGINEERING_GUIDE.md",
        "frontend/README.md",
        "website/README.md",
        "desktop/README.md",
    )
    prohibited_setup_commands = (
        "pip install -r requirements.txt",
        "npm install",
        "--host 0.0.0.0",
        "alembic upgrade",
    )
    for path in active_setup_docs:
        lowered = _read(path).lower()
        for command in prohibited_setup_commands:
            if command in lowered:
                errors.append(f"{path} contains unsupported setup command: {command}")

    guide = _read("docs/ENGINEERING_GUIDE.md")
    required_guide_phrases = (
        "Python 3.12",
        "127.0.0.1:5100",
        "127.0.0.1:5200",
        "127.0.0.1:5300",
        "Production does not use Alembic",
        "one-time lifetime licenses",
        "app backend is never deployed to a cloud service",
        "private draft",
    )
    for phrase in required_guide_phrases:
        if phrase not in guide:
            errors.append(f"docs/ENGINEERING_GUIDE.md is missing: {phrase}")

    vite = _read("frontend/vite.config.js")
    if not re.search(r"host:\s*['\"]127\.0\.0\.1['\"]", vite):
        errors.append("frontend/vite.config.js must default to 127.0.0.1")

    start_script = _read("start.sh")
    if "app.core.network_access" not in start_script or '--host "$BIND_HOST"' not in start_script:
        errors.append("start.sh must derive and pass the explicit local/LAN bind host")

    ci = _read(".github/workflows/ci.yml")
    if "python scripts/verify_documentation_contracts.py" not in ci:
        errors.append("CI must execute the documentation contract verifier")

    retired_alembic = ROOT / "backend/alembic/versions"
    if retired_alembic.exists() and any(retired_alembic.rglob("*.py")):
        errors.append("Retired backend/alembic/versions code must remain absent")
    return errors


def main() -> int:
    errors = verify()
    if errors:
        print("Documentation contract failures:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("Documentation contracts match repository architecture and manifests.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
