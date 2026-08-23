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
    families = payload.get("families")
    features = payload.get("features")
    if (
        not isinstance(tiers, dict)
        or not isinstance(families, dict)
        or not isinstance(features, dict)
    ):
        raise EntitlementManifestError("The entitlement manifest is incomplete.")

    for tier in ("free", "pro", "max"):
        tier_payload = tiers.get(tier)
        if not isinstance(tier_payload, dict):
            raise EntitlementManifestError(f"Missing entitlement tier: {tier}")
        tier_features = tier_payload.get("released_features", [])
        tier_families = tier_payload.get("released_families", [])
        if not isinstance(tier_features, list) or not isinstance(tier_families, list):
            raise EntitlementManifestError(
                f"Tier {tier} has invalid feature or family lists."
            )
        if len(tier_features) != len(set(tier_features)):
            raise EntitlementManifestError(f"Tier {tier} repeats a feature.")
        if len(tier_families) != len(set(tier_families)):
            raise EntitlementManifestError(f"Tier {tier} repeats a family.")
        flattened_grants: list[str] = []
        for family in tier_families:
            definition = families.get(family)
            if (
                not isinstance(definition, dict)
                or definition.get("status") != "released"
                or not isinstance(definition.get("grants"), list)
            ):
                raise EntitlementManifestError(
                    f"Tier {tier} includes an invalid family: {family}"
                )
            flattened_grants.extend(definition["grants"])
        if flattened_grants != tier_features:
            raise EntitlementManifestError(
                f"Tier {tier} feature grants do not match its released families."
            )
        for feature in tier_features:
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


def families_for_tier(tier: str) -> list[str]:
    manifest = entitlement_manifest()
    selected = manifest["tiers"].get(tier, manifest["tiers"]["free"])
    return list(selected["released_families"])


def legacy_features_for_tier(version: int, tier: str) -> list[str] | None:
    versions = entitlement_manifest().get("legacy_feature_sets", {})
    version_payload = versions.get(str(version))
    if not isinstance(version_payload, dict):
        return None
    features = version_payload.get(tier)
    return list(features) if isinstance(features, list) else None


def activation_limit_for_tier(tier: str) -> int:
    manifest = entitlement_manifest()
    selected = manifest["tiers"].get(tier)
    if not selected:
        return 0
    return int(selected["activation_limit"])


def included_hosted_ai_credits() -> int:
    return int(entitlement_manifest().get("included_hosted_ai_credits", 0))
