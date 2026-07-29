from app.core.entitlements import (
    activation_limit_for_tier,
    entitlement_manifest,
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


def test_paid_tiers_have_three_activations_and_no_included_hosted_credits():
    assert activation_limit_for_tier("pro") == 3
    assert activation_limit_for_tier("max") == 3
    assert included_hosted_ai_credits() == 0


def test_max_personal_classifier_is_not_granted_to_pro():
    assert "personal_classifier" not in features_for_tier("pro")
    assert "personal_classifier" in features_for_tier("max")
