#!/usr/bin/env python3
"""Fail CI unless the bundled local-model registry is authentic and consistent."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.local_ai import BUILTIN_MODEL_REGISTRY, load_model_registry  # noqa: E402


def main() -> int:
    models, status = load_model_registry()
    if not status.get("signature_verified"):
        raise SystemExit(f"Model registry verification failed: {status.get('error')}")
    if models != BUILTIN_MODEL_REGISTRY:
        raise SystemExit(
            "Signed registry and the recommendation matrix differ; sign the exact "
            "reviewed model metadata before release."
        )
    print(
        f"Verified signed model registry {status['registry_version']} "
        f"with {len(models)} pinned models."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
