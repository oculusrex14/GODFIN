#!/usr/bin/env python3
"""Generate GODFIN's deterministic CycloneDX SBOM and notice inventory."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import sys
import urllib.parse
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SBOM_PATH = ROOT / "sbom" / "godfin.cdx.json"
NOTICES_PATH = ROOT / "THIRD_PARTY_NOTICES.md"
PYTHON_REVIEW_PATH = ROOT / "supply-chain" / "python-license-review.json"
POLICY_PATH = ROOT / "supply-chain" / "license-policy.json"

PYTHON_LOCKS = {
    "python-runtime": ROOT / "backend" / "requirements-lock.txt",
    "python-test": ROOT / "backend" / "requirements-test-lock.txt",
    "python-build": ROOT / "backend" / "requirements-build-lock.txt",
}
NPM_LOCKS = {
    "npm-frontend": ROOT / "frontend" / "package-lock.json",
    "npm-website": ROOT / "website" / "package-lock.json",
    "npm-desktop": ROOT / "desktop" / "package-lock.json",
    "npm-playwright": ROOT / "playwright-tests" / "package-lock.json",
}
INPUT_PATHS = (*PYTHON_LOCKS.values(), *NPM_LOCKS.values(), PYTHON_REVIEW_PATH, POLICY_PATH)
SPDX_TOKEN = re.compile(r"(?:LicenseRef-[A-Za-z0-9.-]+|[A-Za-z0-9][A-Za-z0-9.-]*)")


def _canonical_python_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass
class Component:
    ecosystem: str
    name: str
    version: str
    purl: str
    license_expression: str
    hashes: set[tuple[str, str]] = field(default_factory=set)
    surfaces: set[str] = field(default_factory=set)
    scopes: set[str] = field(default_factory=set)
    markers: set[str] = field(default_factory=set)

    @property
    def bom_ref(self) -> str:
        return self.purl


def _load_python_licenses() -> dict[tuple[str, str], str]:
    review = json.loads(PYTHON_REVIEW_PATH.read_text(encoding="utf-8"))
    if review.get("schema_version") != 1:
        raise RuntimeError("unsupported Python license review schema")
    licenses: dict[tuple[str, str], str] = {}
    for group in review.get("groups", []):
        expression = str(group.get("expression", "")).strip()
        if not expression:
            raise RuntimeError("a Python license review group has no expression")
        for requirement in group.get("packages", []):
            if "==" not in requirement:
                raise RuntimeError(f"invalid reviewed Python package: {requirement}")
            name, version = requirement.split("==", 1)
            key = (_canonical_python_name(name), version)
            if key in licenses:
                raise RuntimeError(f"duplicate Python license review: {requirement}")
            licenses[key] = expression
    return licenses


def _merge_component(
    components: dict[str, Component], incoming: Component
) -> None:
    existing = components.get(incoming.purl)
    if existing is None:
        components[incoming.purl] = incoming
        return
    if existing.license_expression != incoming.license_expression:
        raise RuntimeError(
            f"license drift for {incoming.purl}: "
            f"{existing.license_expression!r} != {incoming.license_expression!r}"
        )
    existing.hashes.update(incoming.hashes)
    existing.surfaces.update(incoming.surfaces)
    existing.scopes.update(incoming.scopes)
    existing.markers.update(incoming.markers)


def _parse_python_locks(components: dict[str, Component]) -> None:
    reviewed = _load_python_licenses()
    found: set[tuple[str, str]] = set()
    entry = re.compile(r"^([A-Za-z0-9_.-]+)==([^ ;\\]+)(.*)\\$")
    hash_line = re.compile(r"^\s+--hash=(sha256):([a-f0-9]{64})(?: \\)?$")
    scope_by_surface = {
        "python-runtime": "runtime",
        "python-test": "test",
        "python-build": "build",
    }
    for surface, path in PYTHON_LOCKS.items():
        lines = path.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            match = entry.match(line)
            if match is None:
                continue
            name = _canonical_python_name(match.group(1))
            version = match.group(2)
            key = (name, version)
            found.add(key)
            expression = reviewed.get(key)
            if expression is None:
                raise RuntimeError(f"unreviewed Python dependency: {name}=={version}")
            marker = match.group(3).strip()
            if marker.startswith(";"):
                marker = marker[1:].strip()
            hashes: set[tuple[str, str]] = set()
            cursor = index + 1
            while cursor < len(lines):
                hash_match = hash_line.match(lines[cursor])
                if hash_match is None:
                    break
                hashes.add(("SHA-256", hash_match.group(2)))
                cursor += 1
            if not hashes:
                raise RuntimeError(f"unhashed Python dependency: {name}=={version}")
            purl = f"pkg:pypi/{urllib.parse.quote(name)}@{urllib.parse.quote(version)}"
            _merge_component(
                components,
                Component(
                    ecosystem="PyPI",
                    name=name,
                    version=version,
                    purl=purl,
                    license_expression=expression,
                    hashes=hashes,
                    surfaces={surface},
                    scopes={scope_by_surface[surface]},
                    markers={marker} if marker else set(),
                ),
            )
    stale = sorted(set(reviewed) - found)
    if stale:
        formatted = ", ".join(f"{name}=={version}" for name, version in stale)
        raise RuntimeError(f"stale Python license reviews: {formatted}")


def _npm_name_from_path(package_path: str) -> str:
    remainder = package_path.rsplit("node_modules/", 1)[-1]
    parts = remainder.split("/")
    if remainder.startswith("@") and len(parts) >= 2:
        return "/".join(parts[:2])
    return parts[0]


def _npm_hash(integrity: str) -> tuple[str, str] | None:
    if "-" not in integrity:
        return None
    algorithm, encoded = integrity.split("-", 1)
    algorithms = {"sha1": "SHA-1", "sha256": "SHA-256", "sha384": "SHA-384", "sha512": "SHA-512"}
    if algorithm not in algorithms:
        return None
    try:
        content = base64.b64decode(encoded, validate=True).hex()
    except ValueError as exc:
        raise RuntimeError(f"invalid npm integrity hash: {integrity}") from exc
    return algorithms[algorithm], content


def _parse_npm_locks(components: dict[str, Component]) -> None:
    for surface, path in NPM_LOCKS.items():
        lock = json.loads(path.read_text(encoding="utf-8"))
        if lock.get("lockfileVersion") not in {2, 3}:
            raise RuntimeError(f"unsupported npm lock version in {path}")
        for package_path, metadata in sorted(lock.get("packages", {}).items()):
            if not package_path or "node_modules/" not in package_path:
                continue
            version = str(metadata.get("version", "")).strip()
            if not version:
                if metadata.get("link"):
                    continue
                raise RuntimeError(f"npm dependency without version: {package_path}")
            name = _npm_name_from_path(package_path)
            expression = str(metadata.get("license", "")).strip()
            if not expression or expression.upper() == "UNLICENSED":
                raise RuntimeError(f"npm dependency without reviewed license: {name}@{version}")
            encoded_name = urllib.parse.quote(name, safe="")
            purl = f"pkg:npm/{encoded_name}@{urllib.parse.quote(version)}"
            hashes: set[tuple[str, str]] = set()
            if metadata.get("integrity"):
                decoded = _npm_hash(str(metadata["integrity"]))
                if decoded:
                    hashes.add(decoded)
            if not hashes and not metadata.get("resolved", "").startswith("file:"):
                raise RuntimeError(f"npm dependency without integrity hash: {name}@{version}")
            scope = "development" if metadata.get("dev") else "runtime"
            _merge_component(
                components,
                Component(
                    ecosystem="npm",
                    name=name,
                    version=version,
                    purl=purl,
                    license_expression=expression,
                    hashes=hashes,
                    surfaces={surface},
                    scopes={scope},
                ),
            )


def _license_ids(expression: str) -> set[str]:
    ignored = {"AND", "OR", "WITH"}
    return {token for token in SPDX_TOKEN.findall(expression) if token not in ignored}


def _validate_policy(components: dict[str, Component]) -> tuple[dict[str, str], list[Component]]:
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    if policy.get("schema_version") != 1:
        raise RuntimeError("unsupported license policy schema")
    permissive = set(policy.get("permissive_license_ids", []))
    conditional = dict(policy.get("conditional_license_ids", {}))
    exceptions = set(policy.get("allowed_exception_ids", []))
    prohibited = set(policy.get("prohibited_license_ids", []))
    known = permissive | conditional.keys() | exceptions
    conditional_components: list[Component] = []
    for component in components.values():
        ids = _license_ids(component.license_expression)
        forbidden = ids & prohibited
        unknown = ids - known
        if forbidden:
            raise RuntimeError(
                f"prohibited license in {component.purl}: {', '.join(sorted(forbidden))}"
            )
        if unknown:
            raise RuntimeError(
                f"unreviewed license IDs in {component.purl}: {', '.join(sorted(unknown))}"
            )
        if ids & conditional.keys():
            conditional_components.append(component)
    return conditional, sorted(conditional_components, key=lambda item: item.purl)


def _component_dict(component: Component) -> dict[str, Any]:
    properties = [
        {"name": "godfin:dependency:surfaces", "value": ",".join(sorted(component.surfaces))},
        {"name": "godfin:dependency:scopes", "value": ",".join(sorted(component.scopes))},
    ]
    if component.markers:
        properties.append(
            {"name": "godfin:dependency:markers", "value": " | ".join(sorted(component.markers))}
        )
    result: dict[str, Any] = {
        "type": "library",
        "bom-ref": component.bom_ref,
        "name": component.name,
        "version": component.version,
        "scope": "required" if "runtime" in component.scopes else "optional",
        "licenses": [{"expression": component.license_expression}],
        "purl": component.purl,
        "properties": properties,
    }
    if component.hashes:
        result["hashes"] = [
            {"alg": algorithm, "content": content}
            for algorithm, content in sorted(component.hashes)
        ]
    return result


def _build_sbom(components: dict[str, Component]) -> dict[str, Any]:
    desktop_manifest = json.loads(
        (ROOT / "desktop" / "package.json").read_text(encoding="utf-8")
    )
    version = str(desktop_manifest["version"])
    component_dicts = [
        _component_dict(component)
        for component in sorted(components.values(), key=lambda item: item.purl)
    ]
    fingerprint = hashlib.sha256(_json_bytes(component_dicts)).hexdigest()
    serial = uuid.uuid5(uuid.NAMESPACE_URL, f"https://godfin.dev/sbom/{version}/{fingerprint}")
    runtime_refs = sorted(
        component.bom_ref
        for component in components.values()
        if "runtime" in component.scopes
    )
    return {
        "$schema": "https://cyclonedx.org/schema/bom-1.6.schema.json",
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": f"urn:uuid:{serial}",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "bom-ref": f"pkg:generic/godfin@{version}",
                "name": "GODFIN",
                "version": version,
                "licenses": [{"expression": "PolyForm-Noncommercial-1.0.0"}],
            },
            "tools": {
                "components": [
                    {
                        "type": "application",
                        "name": "GODFIN deterministic supply-chain generator",
                        "version": "1",
                    }
                ]
            },
            "properties": [
                {"name": "godfin:input:fingerprint:sha256", "value": fingerprint},
                {"name": "godfin:public-promotion", "value": "requires-approved-legal-clearance"},
            ],
        },
        "components": component_dicts,
        "dependencies": [
            {"ref": f"pkg:generic/godfin@{version}", "dependsOn": runtime_refs}
        ],
    }


def _escape_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _build_notices(
    components: dict[str, Component],
    conditional: dict[str, str],
    conditional_components: list[Component],
) -> str:
    runtime_count = sum("runtime" in item.scopes for item in components.values())
    lines = [
        "# GODFIN Third-Party Dependency Notices",
        "",
        "> Generated deterministically from the checked-in Python and npm lockfiles. This is an engineering inventory, not legal advice. Public promotion is blocked until qualified counsel approves the exact release SBOM in `supply-chain/legal-clearance.json`.",
        "",
        "## Inventory summary",
        "",
        f"- Exact unique components: {len(components)}",
        f"- Components used by a runtime surface: {runtime_count}",
        f"- Components requiring conditional-license review: {len(conditional_components)}",
        "- Application license: PolyForm Noncommercial 1.0.0",
        "",
        "The authoritative machine-readable inventory is `sbom/godfin.cdx.json`. Dependency archives and their complete license files remain authoritative if this generated summary conflicts with upstream terms.",
        "",
        "## Conditional-license obligations",
        "",
    ]
    conditional_ids = sorted(
        {
            license_id
            for component in conditional_components
            for license_id in _license_ids(component.license_expression)
            if license_id in conditional
        }
    )
    if conditional_ids:
        for license_id in conditional_ids:
            lines.append(f"- **{license_id}:** {conditional[license_id]}")
    else:
        lines.append("- None in this lock set.")
    lines.extend(
        [
            "",
            "## Exact dependency inventory",
            "",
            "| Component | Version | Ecosystem | License expression | Scope | Surfaces |",
            "|---|---:|---|---|---|---|",
        ]
    )
    for component in sorted(components.values(), key=lambda item: item.purl):
        lines.append(
            "| "
            + " | ".join(
                _escape_table(value)
                for value in (
                    component.name,
                    component.version,
                    component.ecosystem,
                    component.license_expression,
                    ", ".join(sorted(component.scopes)),
                    ", ".join(sorted(component.surfaces)),
                )
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Reviewed input fingerprints",
            "",
            "| Input | SHA-256 |",
            "|---|---|",
        ]
    )
    for path in sorted(INPUT_PATHS):
        lines.append(f"| `{path.relative_to(ROOT)}` | `{_sha256(path)}` |")
    lines.extend(
        [
            "",
            "## Release rule",
            "",
            "Private draft artifacts may be built with a pending legal-clearance record. A public update-feed promotion must fail unless the record is approved for the exact SBOM SHA-256 and release version. Notices, the SBOM, GODFIN's own license, and the legal-clearance record are bundled into desktop packages and draft release assets.",
            "",
        ]
    )
    return "\n".join(lines)


def generate() -> tuple[bytes, bytes]:
    components: dict[str, Component] = {}
    _parse_python_locks(components)
    _parse_npm_locks(components)
    conditional, conditional_components = _validate_policy(components)
    sbom = _build_sbom(components)
    notices = _build_notices(components, conditional, conditional_components)
    return _json_bytes(sbom), notices.encode("utf-8")


def _check(path: Path, expected: bytes) -> bool:
    if not path.exists():
        print(f"Missing generated artifact: {path.relative_to(ROOT)}", file=sys.stderr)
        return False
    if path.read_bytes() != expected:
        print(f"Generated artifact is stale: {path.relative_to(ROOT)}", file=sys.stderr)
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail if generated files differ")
    args = parser.parse_args()
    try:
        sbom_bytes, notices_bytes = generate()
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"Supply-chain generation failed: {exc}", file=sys.stderr)
        return 1
    if args.check:
        return 0 if _check(SBOM_PATH, sbom_bytes) and _check(NOTICES_PATH, notices_bytes) else 1
    SBOM_PATH.parent.mkdir(parents=True, exist_ok=True)
    SBOM_PATH.write_bytes(sbom_bytes)
    NOTICES_PATH.write_bytes(notices_bytes)
    print(f"Generated {SBOM_PATH.relative_to(ROOT)} and {NOTICES_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
