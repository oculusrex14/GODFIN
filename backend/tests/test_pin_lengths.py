import pytest

from app.core.auth import hash_pin
from app.models.app_setting import AppSetting


@pytest.mark.parametrize("pin", ("4826", "48265", "482650"))
def test_new_pin_accepts_four_to_six_digits(client, pin):
    response = client.post("/api/v1/auth/set-pin", json={"pin": pin})
    assert response.status_code == 200
    status = client.get("/api/v1/auth/status")
    assert status.json()["pin_length"] == len(pin)


def test_new_pin_rejects_more_than_six_digits(client):
    response = client.post("/api/v1/auth/set-pin", json={"pin": "4826507"})
    assert response.status_code == 422


def test_lan_status_does_not_disclose_configured_pin_length(
    client,
    monkeypatch,
):
    response = client.post("/api/v1/auth/set-pin", json={"pin": "482650"})
    assert response.status_code == 200
    monkeypatch.setenv("GODFIN_RUNTIME_MODE", "lan")

    status = client.get("/api/v1/auth/status")

    assert status.status_code == 200
    assert status.json()["is_first_run"] is False
    assert status.json()["pin_length"] is None


def test_legacy_eight_digit_pin_can_unlock(client, db_session):
    first_run = db_session.query(AppSetting).filter_by(key="is_first_run").one()
    first_run.value = "false"
    pin_setting = db_session.query(AppSetting).filter_by(key="pin_hash").one()
    pin_setting.value = hash_pin("48265073")
    db_session.commit()

    unknown_status = client.get("/api/v1/auth/status")
    assert unknown_status.json()["pin_length"] is None
    response = client.post("/api/v1/auth/verify-pin", json={"pin": "48265073"})

    assert response.status_code == 200
    assert response.json()["authenticated"] is True
    migrated_status = client.get("/api/v1/auth/status")
    assert migrated_status.json()["pin_length"] == 8


def test_legacy_eight_digit_pin_can_be_changed(auth_client, db_session):
    pin_setting = db_session.query(AppSetting).filter_by(key="pin_hash").one()
    pin_setting.value = hash_pin("48265073")
    db_session.commit()

    response = auth_client.post(
        "/api/v1/auth/change-pin",
        json={"current_pin": "48265073", "new_pin": "482650"},
    )

    assert response.status_code == 200
    status = auth_client.get("/api/v1/auth/status")
    assert status.json()["pin_length"] == 6
    verify = auth_client.post("/api/v1/auth/verify-pin", json={"pin": "482650"})
    assert verify.status_code == 200
