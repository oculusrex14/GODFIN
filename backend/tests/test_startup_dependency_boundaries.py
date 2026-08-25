"""Cold-start contracts for request-only integration dependencies."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def test_api_boot_does_not_load_request_only_integrations():
    backend_root = Path(__file__).resolve().parents[1]
    modules = [
        "app.core.gmail_service",
        "app.core.ingestion",
        "app.core.mapped_import",
        "app.core.parsers.registry",
        "google_auth_oauthlib.flow",
        "googleapiclient.discovery",
    ]
    script = (
        "import json, sys; import app.main; "
        f"print(json.dumps({modules!r})); "
        f"print(json.dumps([name for name in {modules!r} if name in sys.modules]))"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=backend_root,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    output = result.stdout.strip().splitlines()
    assert json.loads(output[-1]) == []
