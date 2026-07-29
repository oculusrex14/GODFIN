from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any


class EntitlementManifestError(RuntimeError):
    pass


def _manifest_path() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "shared" / "entitlements.json"
    return Path(__file__).resolve().parents[3] / "shared" / "entitlements.json"


@lru_cache(maxsize=1)
def entitlement_manifest() -> dict[str, Any]:
    try:
        payload = json.loads(_manifest_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EntitlementManifestError(
            "The shared entitlement manifest could not be loaded."
        ) from exc

    tiers = payload.get("tiers")
    features = payload.get("features")
    if not isinstance(tiers, dict) or not isinstance(features, dict):
        raise EntitlementManifestError("The entitlement manifest is incomplete.")

    for tier in ("free", "pro", "max"):
        tier_payload = tiers.get(tier)
        if not isinstance(tier_payload, dict):
            raise EntitlementManifestError(f"Missing entitlement tier: {tier}")
        for feature in tier_payload.get("released_features", []):
            definition = features.get(feature)
            if not isinstance(definition, dict) or definition.get("status") != "released":
                raise EntitlementManifestError(
                    f"Tier {tier} includes an unreleased feature: {feature}"
                )
    return payload


def features_for_tier(tier: str) -> list[str]:
    manifest = entitlement_manifest()
    selected = manifest["tiers"].get(tier, manifest["tiers"]["free"])
    return list(selected["released_features"])


def activation_limit_for_tier(tier: str) -> int:
    manifest = entitlement_manifest()
    selected = manifest["tiers"].get(tier)
    if not selected:
        return 0
    return int(selected["activation_limit"])


def included_hosted_ai_credits() -> int:
    return int(entitlement_manifest().get("included_hosted_ai_credits", 0))
