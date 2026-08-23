from pathlib import Path

from app.core.entitlements import (
    _manifest_path,
    activation_limit_for_tier,
    entitlement_manifest,
    families_for_tier,
    features_for_tier,
    included_hosted_ai_credits,
)


def test_manifest_only_assigns_released_features():
    manifest = entitlement_manifest()
    for tier in manifest["tiers"].values():
        assert all(
            manifest["features"][feature]["status"] == "released"
            for feature in tier["released_features"]
        )


def test_capability_family_split_is_60_75_100_percent():
    assert len(families_for_tier("free")) == 12
    assert len(families_for_tier("pro")) == 15
    assert len(families_for_tier("max")) == 20


def test_every_tier_feature_list_is_exactly_flattened_family_grants():
    manifest = entitlement_manifest()
    for tier in ("free", "pro", "max"):
        expected = [
            feature
            for family in families_for_tier(tier)
            for feature in manifest["families"][family]["grants"]
        ]
        assert features_for_tier(tier) == expected


def test_pro_automation_is_separate_from_max_ai_and_tax_features():
    pro = set(features_for_tier("pro"))
    maximum = set(features_for_tier("max"))

    assert {
        "multiple_accounts",
        "batch_statement_import",
        "generic_mapped_import",
        "gmail_sync",
        "advanced_reports",
        "reference_fx",
    } <= pro
    assert {"ai_classification", "ai_advisor", "ca_tax_pack"}.isdisjoint(pro)
    assert {"ai_classification", "ai_advisor", "ca_tax_pack"} <= maximum


def test_core_safety_and_owned_data_export_are_never_gated():
    core = set(features_for_tier("free"))
    assert {"data_recovery_export", "csv_export", "local_sqlite"} <= core


def test_paid_tiers_have_three_activations_and_no_included_hosted_credits():
    assert activation_limit_for_tier("pro") == 3
    assert activation_limit_for_tier("max") == 3
    assert included_hosted_ai_credits() == 0


def test_max_personal_classifier_is_not_granted_to_pro():
    assert "personal_classifier" not in features_for_tier("pro")
    assert "personal_classifier" in features_for_tier("max")


def test_phase4_premium_features_are_max_only():
    assert "net_worth" not in features_for_tier("pro")
    assert "behavior_insights" not in features_for_tier("pro")
    assert "net_worth" in features_for_tier("max")
    assert "behavior_insights" in features_for_tier("max")


def test_manifest_path_uses_pyinstaller_bundle_root(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.entitlements.sys.frozen", True, raising=False)
    monkeypatch.setattr(
        "app.core.entitlements.sys._MEIPASS",
        str(tmp_path),
        raising=False,
    )

    assert _manifest_path() == Path(tmp_path) / "shared" / "entitlements.json"
