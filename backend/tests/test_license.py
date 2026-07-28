from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.core.encryption import decrypt
from app.core.license import LICENSE_FEATURES, license_status
from app.models.app_setting import AppSetting

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
            {
                "valid": True,
                "tier": "pro",
                "monthly_credits": 500,
                "topup_credits": 1200,
            }
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
    assert payload["monthly_credits"] == 500
    assert payload["topup_credits"] == 1200
    assert TEST_KEY not in str(payload)
    assert request_payload["machine_id"]
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


def test_paid_features_expire_after_offline_grace(db_session):
    verified_at = datetime(2026, 1, 1, tzinfo=UTC)
    _set(db_session, "license_tier", "max")
    _set(db_session, "license_status", "active")
    _set(db_session, "license_verified_at", verified_at.isoformat())

    within_grace = license_status(
        db_session,
        now=verified_at + timedelta(days=29),
    )
    expired = license_status(
        db_session,
        now=verified_at + timedelta(days=31),
    )

    assert within_grace["tier"] == "max"
    assert within_grace["valid"] is True
    assert expired["tier"] == "free"
    assert expired["status"] == "verification_required"


def test_core_cannot_enable_paid_ai_feature(auth_client):
    response = auth_client.post("/api/v1/system/embeddings/enable")

    assert response.status_code == 403
    assert response.json()["code"] == "LICENSE_REQUIRED"
