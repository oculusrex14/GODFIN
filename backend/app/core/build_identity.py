"""Support-safe identity for the exact GODFIN build currently running."""

from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from app.core.config import settings
from app.core.entitlements import entitlement_manifest
from app.core.parsers.registry import PARSER_REGISTRY_VERSION
from app.core.startup_migrations import CURRENT_SCHEMA_REVISION


_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_CHANNEL_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,40}$")


def _generated_identity_path() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "shared" / "build-identity.json"
    return Path(__file__).resolve().parents[2] / "build" / "build-identity.json"


def _generated_identity() -> dict[str, str]:
    try:
        payload = json.loads(_generated_identity_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {
        str(key): str(value)
        for key, value in payload.items()
        if isinstance(key, str) and isinstance(value, str)
    }


def _development_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parents[3],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    candidate = result.stdout.strip().lower()
    return candidate if _SHA_PATTERN.fullmatch(candidate) else "unknown"


@lru_cache(maxsize=1)
def build_identity() -> dict[str, object]:
    generated = _generated_identity()
    sha_candidate = (
        os.environ.get("GODFIN_BUILD_SHA")
        or generated.get("full_sha")
        or _development_sha()
    ).strip().lower()
    full_sha = sha_candidate if _SHA_PATTERN.fullmatch(sha_candidate) else "unknown"
    channel_candidate = (
        os.environ.get("GODFIN_BUILD_CHANNEL")
        or generated.get("channel")
        or ("private" if getattr(sys, "frozen", False) else "development")
    ).strip()
    channel = (
        channel_candidate
        if _CHANNEL_PATTERN.fullmatch(channel_candidate)
        else "unknown"
    )
    built_at = (
        os.environ.get("GODFIN_BUILD_TIMESTAMP")
        or generated.get("built_at_utc")
        or "unknown"
    ).strip()[:40]
    version = (
        os.environ.get("GODFIN_APP_VERSION")
        or generated.get("version")
        or settings.VERSION
    ).strip()[:32]
    host = urlsplit(settings.LICENSE_API_URL).hostname or "unknown"
    return {
        "version": version,
        "full_sha": full_sha,
        "short_sha": full_sha[:12] if full_sha != "unknown" else "unknown",
        "channel": channel,
        "built_at_utc": built_at,
        "schema_revision": CURRENT_SCHEMA_REVISION,
        "entitlement_manifest_version": int(
            entitlement_manifest().get("schema_version", 0)
        ),
        "parser_registry_version": PARSER_REGISTRY_VERSION,
        "os": platform.system() or "unknown",
        "architecture": platform.machine() or "unknown",
        "license_api_host": host,
    }
