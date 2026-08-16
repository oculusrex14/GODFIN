from __future__ import annotations

import copy
import base64
import json
from datetime import UTC, datetime, timedelta

from app.core.encryption import decrypt, encrypt
from app.core.license import LICENSE_FEATURES, license_status
from app.core.config import settings
from app.core.license_entitlement import (
    EntitlementValidationError,
    public_key_manifest,
    verify_entitlement_envelope,
)
from app.models.app_setting import AppSetting
from tests.license_helpers import (
    TEST_KEY_VERSION,
    install_test_license,
    signed_entitlement,
    signed_server_response,
    test_public_key_manifest_json as public_key_manifest_json_for_tests,
)

TEST_KEY = "GODFIN-PRO-AAAAA-BBBBB-CCCCC-DDDDD-EEEEE"


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


def _set(db, key, value):
    setting = db.query(AppSetting).filter_by(key=key).first()
    setting.value = value
    db.commit()


def test_license_defaults_to_core_and_never_exposes_key(auth_client):
    response = auth_client.get("/api/v1/license")

    assert response.status_code == 200
    assert response.json()["tier"] == "free"
    assert response.json()["valid"] is False
    settings_response = auth_client.get("/api/v1/settings")
    assert "license_key" not in settings_response.json()


def test_activate_encrypts_key_and_unlocks_server_features(
    auth_client, db_session, monkeypatch, tmp_path
):
    request_payload = {}

    def fake_post(_url, **kwargs):
        request_payload.update(kwargs["json"])
        return FakeResponse(
            signed_server_response(
                "pro",
                machine_id=kwargs["json"]["machine_id"],
            )
        )

    monkeypatch.setattr("app.core.license.httpx.post", fake_post)
    monkeypatch.setenv("GODFIN_MACHINE_ID_FILE", str(tmp_path / ".machine_id"))

    response = auth_client.post(
        "/api/v1/license/activate",
        json={"license_key": TEST_KEY.lower()},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["tier"] == "pro"
    assert payload["features"] == LICENSE_FEATURES["pro"]
    assert payload["monthly_credits"] == 0
    assert payload["hosted_credits_included"] == 0
    assert payload["topup_credits"] == 0
    assert payload["entitlement_integrity"] == "verified"
    assert TEST_KEY not in str(payload)
    assert request_payload["machine_id"]
    assert request_payload["device_label"]
    assert "transactions" not in request_payload

    db_session.expire_all()
    stored = db_session.query(AppSetting).filter_by(key="license_key").one().value
    assert stored != TEST_KEY
    assert decrypt(stored) == TEST_KEY


def test_failed_activation_does_not_replace_current_license(
    auth_client, db_session, monkeypatch
):
    _set(db_session, "license_tier", "pro")
    monkeypatch.setattr(
        "app.core.license.httpx.post",
        lambda *_args, **_kwargs: FakeResponse(
            {"valid": False, "code": "LICENSE_NOT_FOUND", "message": "Not found."},
            403,
        ),
    )

    response = auth_client.post(
        "/api/v1/license/activate",
        json={"license_key": TEST_KEY},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "LICENSE_NOT_FOUND"
    db_session.expire_all()
    assert (
        db_session.query(AppSetting).filter_by(key="license_tier").one().value
        == "pro"
    )


def test_license_verification_falls_back_only_for_server_failure(
    auth_client, monkeypatch
):
    primary = "https://godfin.dev/api/license/verify"
    fallback = "https://godfin.vercel.app/api/license/verify"
    calls = []

    def fake_post(url, **kwargs):
        calls.append(url)
        if url == primary:
            return FakeResponse({"message": "Temporary failure"}, 503)
        return FakeResponse(
            signed_server_response(
                "max",
                machine_id=kwargs["json"]["machine_id"],
            )
        )

    monkeypatch.setattr(settings, "LICENSE_API_URL", primary)
    monkeypatch.setattr(settings, "LICENSE_API_FALLBACK_URL", fallback)
    monkeypatch.setattr("app.core.license.httpx.post", fake_post)

    response = auth_client.post(
        "/api/v1/license/activate",
        json={"license_key": TEST_KEY},
    )

    assert response.status_code == 200
    assert response.json()["tier"] == "max"
    assert calls == [primary, fallback]


def test_invalid_license_response_never_uses_fallback(auth_client, monkeypatch):
    primary = "https://godfin.dev/api/license/verify"
    fallback = "https://godfin.vercel.app/api/license/verify"
    calls = []

    def fake_post(url, **_kwargs):
        calls.append(url)
        return FakeResponse(
            {"valid": False, "code": "LICENSE_NOT_FOUND", "message": "Not found."},
            403,
        )

    monkeypatch.setattr(settings, "LICENSE_API_URL", primary)
    monkeypatch.setattr(settings, "LICENSE_API_FALLBACK_URL", fallback)
    monkeypatch.setattr("app.core.license.httpx.post", fake_post)

    response = auth_client.post(
        "/api/v1/license/activate",
        json={"license_key": TEST_KEY},
    )

    assert response.status_code == 403
    assert calls == [primary]


def test_license_server_message_and_unknown_code_are_never_reflected(
    auth_client,
    monkeypatch,
):
    leaked = "/Users/private/license.db?token=server-secret"
    monkeypatch.setattr(
        "app.core.license.httpx.post",
        lambda *_args, **_kwargs: FakeResponse(
            {
                "valid": False,
                "code": "INJECTED_SERVER_CODE",
                "message": leaked,
            },
            403,
        ),
    )

    response = auth_client.post(
        "/api/v1/license/activate",
        json={"license_key": TEST_KEY},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "LICENSE_INVALID"
    assert response.json()["message"] == "This license could not be verified."
    assert leaked not in response.text


def test_license_server_unhashable_code_and_unsigned_success_fail_safely(
    auth_client,
    monkeypatch,
):
    responses = iter(
        [
            FakeResponse(
                {
                    "valid": False,
                    "code": ["malformed"],
                    "message": "/private/license/path",
                },
                403,
            ),
            FakeResponse(
                {
                    "valid": True,
                    "tier": "max",
                }
            ),
        ]
    )
    monkeypatch.setattr(
        "app.core.license.httpx.post",
        lambda *_args, **_kwargs: next(responses),
    )

    invalid = auth_client.post(
        "/api/v1/license/activate",
        json={"license_key": TEST_KEY},
    )
    malformed = auth_client.post(
        "/api/v1/license/activate",
        json={"license_key": TEST_KEY},
    )

    assert invalid.status_code == 403
    assert invalid.json()["code"] == "LICENSE_INVALID"
    assert "/private/license/path" not in invalid.text
    assert malformed.status_code == 502
    assert malformed.json()["code"] == "LICENSE_ENTITLEMENT_INVALID"


def test_paid_features_expire_when_signed_entitlement_expires(db_session):
    verified_at = datetime(2026, 1, 1, tzinfo=UTC)
    install_test_license(
        db_session,
        "max",
        issued_at=verified_at,
        expires_at=verified_at + timedelta(days=7),
    )

    within_grace = license_status(
        db_session,
        now=verified_at + timedelta(days=6),
    )
    expired = license_status(
        db_session,
        now=verified_at + timedelta(days=8),
    )

    assert within_grace["tier"] == "max"
    assert within_grace["valid"] is True
    assert expired["tier"] == "free"
    assert expired["status"] == "verification_required"


def test_editing_legacy_license_flags_cannot_unlock_paid_features(db_session):
    _set(db_session, "license_tier", "max")
    _set(db_session, "license_status", "active")
    _set(db_session, "license_verified_at", datetime.now(UTC).isoformat())

    status = license_status(db_session)

    assert status["tier"] == "free"
    assert status["valid"] is False


def test_signed_entitlement_rejects_tampering_and_wrong_machine(db_session):
    envelope = signed_entitlement("max")
    tampered = copy.deepcopy(envelope)
    payload = json.loads(
        base64.urlsafe_b64decode(
            str(tampered["payload"]) + "=" * (-len(str(tampered["payload"])) % 4)
        )
    )
    payload["tier"] = "pro"
    tampered["payload"] = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    ).decode().rstrip("=")
    _set(db_session, "license_entitlement", json.dumps(tampered))
    assert license_status(db_session)["tier"] == "free"

    wrong_machine = signed_entitlement("max", machine_id="other-installation")
    _set(db_session, "license_entitlement", json.dumps(wrong_machine))
    status = license_status(db_session)
    assert status["tier"] == "free"
    assert status["entitlement_integrity"] == "LICENSE_MACHINE_MISMATCH"


def test_signed_entitlement_rejects_future_and_unknown_key(db_session):
    now = datetime.now(UTC)
    future = signed_entitlement(
        "pro",
        issued_at=now + timedelta(hours=1),
        expires_at=now + timedelta(days=2),
    )
    _set(db_session, "license_entitlement", json.dumps(future))
    assert license_status(db_session, now=now)["entitlement_integrity"] == (
        "LICENSE_ENTITLEMENT_FUTURE"
    )

    unknown = signed_entitlement("pro", key_version="unknown-v9")
    _set(db_session, "license_entitlement", json.dumps(unknown))
    assert license_status(db_session)["entitlement_integrity"] == (
        "LICENSE_SIGNING_KEY_UNKNOWN"
    )


def test_signed_entitlement_rejects_modified_features_and_truncated_signature(
    db_session,
):
    wrong_features = signed_entitlement(
        "max",
        claim_overrides={"features": LICENSE_FEATURES["pro"]},
    )
    _set(db_session, "license_entitlement", json.dumps(wrong_features))
    assert license_status(db_session)["entitlement_integrity"] == (
        "LICENSE_ENTITLEMENT_INVALID"
    )

    truncated = signed_entitlement("pro")
    truncated["signature"] = str(truncated["signature"])[:-4]
    _set(db_session, "license_entitlement", json.dumps(truncated))
    assert license_status(db_session)["entitlement_integrity"] == (
        "LICENSE_SIGNATURE_INVALID"
    )


def test_signed_entitlement_rejects_excessive_lifetime_and_noninteger_state():
    issued_at = datetime.now(UTC)
    too_long = signed_entitlement(
        "pro",
        machine_id="test-installation",
        issued_at=issued_at,
        expires_at=issued_at + timedelta(days=32),
    )
    invalid_state = signed_entitlement(
        "pro",
        machine_id="test-installation",
        claim_overrides={"license_state_version": 1.5},
    )

    for envelope in (too_long, invalid_state):
        try:
            verify_entitlement_envelope(envelope, machine_id="test-installation")
        except EntitlementValidationError as exc:
            assert exc.code == "LICENSE_ENTITLEMENT_INVALID"
        else:
            raise AssertionError("Invalid signed entitlement was accepted")


def test_signing_key_overlap_is_accepted_and_retired_key_is_rejected(monkeypatch):
    manifest = json.loads(public_key_manifest_json_for_tests())
    manifest["keys"][TEST_KEY_VERSION]["status"] = "overlap"
    monkeypatch.setenv("GODFIN_LICENSE_PUBLIC_KEYS_JSON", json.dumps(manifest))
    public_key_manifest.cache_clear()
    envelope = signed_entitlement("pro", machine_id="test-installation")
    try:
        assert verify_entitlement_envelope(
            envelope,
            machine_id="test-installation",
        )["tier"] == "pro"
        manifest["keys"][TEST_KEY_VERSION]["status"] = "retired"
        monkeypatch.setenv("GODFIN_LICENSE_PUBLIC_KEYS_JSON", json.dumps(manifest))
        public_key_manifest.cache_clear()
        try:
            verify_entitlement_envelope(
                envelope,
                machine_id="test-installation",
            )
        except EntitlementValidationError as exc:
            assert exc.code == "LICENSE_SIGNING_KEY_UNKNOWN"
        else:
            raise AssertionError("Retired entitlement key was accepted")
    finally:
        public_key_manifest.cache_clear()


def test_authoritative_reverify_revocation_clears_paid_entitlement(
    auth_client,
    db_session,
    monkeypatch,
):
    install_test_license(db_session, "max")
    _set(db_session, "license_key", encrypt(TEST_KEY))
    monkeypatch.setattr(
        "app.core.license.httpx.post",
        lambda *_args, **_kwargs: FakeResponse(
            {"valid": False, "code": "LICENSE_REVOKED"},
            403,
        ),
    )

    response = auth_client.post("/api/v1/license/verify")

    assert response.status_code == 403
    db_session.expire_all()
    assert (
        db_session.query(AppSetting)
        .filter_by(key="license_entitlement")
        .one()
        .value
        == ""
    )
    status = license_status(db_session)
    assert status["tier"] == "free"
    assert status["status"] == "revoked"


def test_packaged_build_ignores_license_endpoint_overrides(monkeypatch):
    from app.core.license import _license_verification_endpoints

    monkeypatch.setenv("GODFIN_PACKAGED", "1")
    monkeypatch.setattr(settings, "LICENSE_API_URL", "https://attacker.invalid/verify")
    monkeypatch.setattr(settings, "LICENSE_API_FALLBACK_URL", "https://evil.invalid/verify")

    assert _license_verification_endpoints() == [
        "https://godfin.dev/api/license/verify",
        "https://godfin.vercel.app/api/license/verify",
    ]


def test_frozen_backend_ignores_license_endpoint_overrides(monkeypatch):
    import app.core.license as license_module

    monkeypatch.delenv("GODFIN_PACKAGED", raising=False)
    monkeypatch.setattr(license_module.sys, "frozen", True, raising=False)
    monkeypatch.setattr(settings, "LICENSE_API_URL", "https://attacker.invalid/verify")

    assert license_module._license_verification_endpoints() == [
        "https://godfin.dev/api/license/verify",
        "https://godfin.vercel.app/api/license/verify",
    ]


def test_packaged_build_ignores_public_key_override(monkeypatch):
    monkeypatch.setenv("GODFIN_PACKAGED", "1")
    monkeypatch.setenv(
        "GODFIN_LICENSE_PUBLIC_KEYS_JSON",
        '{"schema_version":1,"keys":{"attacker":{"status":"active"}}}',
    )
    public_key_manifest.cache_clear()
    try:
        assert "attacker" not in public_key_manifest()["keys"]
    finally:
        monkeypatch.setenv("GODFIN_PACKAGED", "0")
        public_key_manifest.cache_clear()


def test_core_cannot_enable_paid_ai_feature(auth_client):
    response = auth_client.post("/api/v1/system/embeddings/enable")

    assert response.status_code == 403
    assert response.json()["code"] == "LICENSE_REQUIRED"
