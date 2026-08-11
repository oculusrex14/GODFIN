from __future__ import annotations

import ast
import hashlib
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

import app.core.auth as auth_core
from app.core.auth import (
    PIN_HASH_ALGORITHM,
    PIN_HASH_ITERATIONS,
    PIN_HASH_USABILITY_BUDGET_SECONDS,
    hash_pin,
    hash_token,
    pin_hash_needs_upgrade,
    verify_pin_hash,
)
from app.core.pin_security import (
    LOCAL_DEVICE_SCOPE,
    PIN_BACKOFF_SECONDS,
    RATE_LIMIT_WINDOW_SECONDS,
)
from app.core.time import utcnow_naive
from app.models.app_setting import AppSetting
from app.models.audit_log import AuditLog
from app.models.pin_attempt import PinAttempt
from app.models.session import AuthSession


def test_auth_status_first_run(client):
    resp = client.get("/api/v1/auth/status")
    assert resp.status_code == 200
    assert resp.json()["is_first_run"] is True
    assert resp.json()["pin_length"] is None


def test_set_pin(client):
    resp = client.post("/api/v1/auth/set-pin", json={"pin": "4826"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["authenticated"] is True
    assert data["token"] is not None


@pytest.mark.parametrize("pin", ["4826", "48261", "482619"])
def test_set_pin_accepts_four_to_six_digits(client, pin):
    response = client.post("/api/v1/auth/set-pin", json={"pin": pin})
    assert response.status_code == 200
    assert client.get("/api/v1/auth/status").json()["pin_length"] == len(pin)


def test_set_pin_invalid_format(client):
    resp = client.post("/api/v1/auth/set-pin", json={"pin": "abc"})
    assert resp.status_code == 422


@pytest.mark.parametrize(
    "pin",
    [
        "1234", "4321", "1111", "123456", "654321",
        "3434", "121212", "2580", "1999",
    ],
)
def test_new_pin_rejects_common_or_trivial_values(client, pin):
    response = client.post("/api/v1/auth/set-pin", json={"pin": pin})
    assert response.status_code == 400
    assert "too simple" in response.json()["detail"]


def test_new_pin_hash_uses_versioned_current_work_factor():
    stored = hash_pin("4826")
    assert stored.startswith(f"{PIN_HASH_ALGORITHM}$1${PIN_HASH_ITERATIONS}$")
    assert verify_pin_hash("4826", stored) is True
    assert verify_pin_hash("5937", stored) is False


@pytest.mark.parametrize(
    "stored",
    [
        "",
        "not-a-hash",
        "pbkdf2-sha256$2$600000$00$00",
        "pbkdf2-sha256$1$99999$00$00",
        "pbkdf2-sha256$1$2000001$00$00",
        "pbkdf2-sha256$1$600000$not-hex$also-not-hex",
        "00:00",
    ],
)
def test_pin_hash_rejects_malformed_or_unsupported_parameters(stored):
    assert verify_pin_hash("4826", stored) is False


def test_weaker_versioned_pin_hash_is_accepted_only_for_rehash():
    salt = b"weaker-pin-salt!"
    digest = hashlib.pbkdf2_hmac("sha256", b"4826", salt, 100_000)
    stored = f"{PIN_HASH_ALGORITHM}$1$100000${salt.hex()}${digest.hex()}"
    assert verify_pin_hash("4826", stored) is True
    assert pin_hash_needs_upgrade(stored) is True


def test_pin_hash_uses_timing_safe_comparison(monkeypatch):
    stored = hash_pin("4826")
    original = auth_core.hmac.compare_digest
    comparisons = []

    def recording_compare(left, right):
        comparisons.append((len(left), len(right)))
        return original(left, right)

    monkeypatch.setattr(auth_core.hmac, "compare_digest", recording_compare)
    assert verify_pin_hash("4826", stored) is True
    assert comparisons == [(32, 32)]


def test_pin_hash_stays_within_explicit_local_usability_budget():
    started = time.perf_counter()
    stored = hash_pin("4826")
    elapsed = time.perf_counter() - started
    assert stored.startswith(f"{PIN_HASH_ALGORITHM}$1${PIN_HASH_ITERATIONS}$")
    assert elapsed < PIN_HASH_USABILITY_BUDGET_SECONDS


def test_legacy_pin_hash_rehashes_after_successful_unlock(client, db_session):
    client.post("/api/v1/auth/set-pin", json={"pin": "4826"})
    salt = b"legacy-pin-salt!"
    digest = hashlib.pbkdf2_hmac("sha256", b"1234", salt, 100_000)
    legacy = f"{salt.hex()}:{digest.hex()}"
    setting = db_session.query(AppSetting).filter_by(key="pin_hash").one()
    setting.value = legacy
    db_session.commit()

    response = client.post("/api/v1/auth/verify-pin", json={"pin": "1234"})
    assert response.status_code == 200
    db_session.expire_all()
    upgraded = db_session.query(AppSetting).filter_by(key="pin_hash").one().value
    assert upgraded.startswith(f"{PIN_HASH_ALGORITHM}$1${PIN_HASH_ITERATIONS}$")
    assert upgraded != legacy


def test_set_pin_only_once(client):
    client.post("/api/v1/auth/set-pin", json={"pin": "4826"})
    resp = client.post("/api/v1/auth/set-pin", json={"pin": "5678"})
    assert resp.status_code == 400


def test_verify_pin_correct(client):
    client.post("/api/v1/auth/set-pin", json={"pin": "4826"})
    resp = client.post("/api/v1/auth/verify-pin", json={"pin": "4826"})
    assert resp.status_code == 200
    assert resp.json()["authenticated"] is True
    assert resp.json()["token"] is not None


def test_verify_pin_wrong(client):
    client.post("/api/v1/auth/set-pin", json={"pin": "4826"})
    # Use a non-weak PIN ( avoids 400 from format validation)
    resp = client.post("/api/v1/auth/verify-pin", json={"pin": "9876"})
    assert resp.status_code == 401


def test_change_pin(auth_client):
    resp = auth_client.post(
        "/api/v1/auth/change-pin",
        json={"current_pin": "4826", "new_pin": "5937"},
    )
    assert resp.status_code == 200
    assert resp.json()["authenticated"] is True
    # Verify new PIN works
    resp2 = auth_client.post("/api/v1/auth/verify-pin", json={"pin": "5937"})
    assert resp2.status_code == 200


def test_change_pin_wrong_current(auth_client):
    resp = auth_client.post(
        "/api/v1/auth/change-pin",
        json={"current_pin": "9876", "new_pin": "5678"},
    )
    assert resp.status_code == 403


def test_change_pin_requires_auth(client):
    resp = client.post(
        "/api/v1/auth/change-pin",
        json={"current_pin": "4826", "new_pin": "9876"},
    )
    assert resp.status_code == 401


def test_logout(auth_client, db_session):
    token = auth_client.headers["Authorization"].removeprefix("Bearer ")
    resp = auth_client.post("/api/v1/auth/logout")
    assert resp.status_code == 200
    assert resp.json()["status"] == "logged_out"
    assert db_session.query(AuthSession).filter_by(token_hash=hash_token(token)).first() is None


def test_sessions_are_hashed_and_capped_at_three(client, db_session):
    first = client.post("/api/v1/auth/set-pin", json={"pin": "4826"}).json()["token"]
    issued = [first]
    for _ in range(3):
        issued.append(
            client.post("/api/v1/auth/verify-pin", json={"pin": "4826"}).json()["token"]
        )

    sessions = db_session.query(AuthSession).order_by(AuthSession.created_at).all()
    assert len(sessions) == 3
    persisted_hashes = {session.token_hash for session in sessions}
    assert all(token not in persisted_hashes for token in issued)
    assert hash_token(first) not in persisted_hashes
    assert hash_token(issued[-1]) in persisted_hashes


def test_expired_session_is_rejected(client, db_session):
    token = client.post("/api/v1/auth/set-pin", json={"pin": "4826"}).json()["token"]
    session = db_session.query(AuthSession).filter_by(token_hash=hash_token(token)).one()
    session.expires_at = utcnow_naive() - timedelta(seconds=1)
    db_session.commit()

    response = client.get(
        "/api/v1/settings",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401
    assert db_session.query(AuthSession).filter_by(token_hash=hash_token(token)).first() is None


def test_pin_rate_limit_persists_in_database(client, db_session, monkeypatch):
    now = [datetime(2026, 1, 1, 12, 0, 0)]
    monkeypatch.setattr("app.core.pin_security._utcnow", lambda: now[0])
    client.post("/api/v1/auth/set-pin", json={"pin": "4826"})
    for index in range(5):
        response = client.post("/api/v1/auth/verify-pin", json={"pin": "9876"})
        assert response.status_code == 401
        db_session.expire_all()
        device_attempt = db_session.query(PinAttempt).filter_by(
            client_ip=LOCAL_DEVICE_SCOPE
        ).one()
        delay = PIN_BACKOFF_SECONDS[index]
        if delay:
            assert int((device_attempt.blocked_until - now[0]).total_seconds()) == delay
        else:
            assert device_attempt.blocked_until is None
        if index < 4:
            now[0] += timedelta(seconds=10)

    attempt = db_session.query(PinAttempt).filter_by(client_ip="testclient").one()
    assert attempt.failed_attempts == 5
    assert attempt.blocked_until is not None
    device_attempt = db_session.query(PinAttempt).filter_by(
        client_ip=LOCAL_DEVICE_SCOPE
    ).one()
    assert device_attempt.failed_attempts == 5
    assert device_attempt.blocked_until is not None

    blocked = client.post("/api/v1/auth/verify-pin", json={"pin": "4826"})
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) > 0

    failures = db_session.query(AuditLog).filter_by(
        field_changed="pin_security"
    ).order_by(AuditLog.created_at).all()
    assert len(failures) == 5
    assert failures[-1].new_value == "lockout:unlock"
    assert all("9876" not in (event.new_value or "") for event in failures)

    now[0] += timedelta(seconds=RATE_LIMIT_WINDOW_SECONDS + 1)
    unlocked = client.post("/api/v1/auth/verify-pin", json={"pin": "4826"})
    assert unlocked.status_code == 200
    assert db_session.query(PinAttempt).count() == 0


def test_untrusted_forwarded_for_is_ignored(client, db_session):
    client.post("/api/v1/auth/set-pin", json={"pin": "4826"})
    client.post(
        "/api/v1/auth/verify-pin",
        json={"pin": "9876"},
        headers={"X-Forwarded-For": "203.0.113.50"},
    )
    assert db_session.query(PinAttempt).filter_by(client_ip="testclient").count() == 1
    assert db_session.query(PinAttempt).filter_by(client_ip="203.0.113.50").count() == 0


def test_sensitive_endpoint_hopping_cannot_bypass_pin_throttle(
    auth_client,
    db_session,
    monkeypatch,
):
    now = [datetime(2026, 1, 1, 12, 0, 0)]
    monkeypatch.setattr("app.core.pin_security._utcnow", lambda: now[0])
    for _ in range(4):
        response = auth_client.post(
            "/api/v1/settings/reset-data",
            json={"pin": "9999"},
        )
        assert response.status_code == 403
        now[0] += timedelta(seconds=10)
    response = auth_client.post(
        "/api/v1/settings/classification-memory/reset",
        json={"pin": "9999"},
    )
    assert response.status_code == 403

    db_session.expire_all()
    device_attempt = db_session.query(PinAttempt).filter_by(
        client_ip=LOCAL_DEVICE_SCOPE
    ).one()
    assert device_attempt.failed_attempts == 5

    blocked = auth_client.put(
        "/api/v1/settings/preferences/network-access",
        json={"enabled": True, "current_pin": "4826"},
    )
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) > 0

    events = [
        row.new_value
        for row in db_session.query(AuditLog)
        .filter_by(field_changed="pin_security")
        .order_by(AuditLog.created_at)
        .all()
    ]
    assert events[:4] == ["failure:reset_all_data"] * 4
    assert events[-1] == "lockout:reset_classification_memory"


def test_every_sensitive_pin_call_is_action_labelled():
    endpoint_dir = Path(__file__).parents[1] / "app" / "api" / "v1" / "endpoints"
    actions = set()
    for path in endpoint_dir.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Name) or node.func.id != "require_current_pin":
                continue
            action = next(
                (keyword.value for keyword in node.keywords if keyword.arg == "action"),
                None,
            )
            assert isinstance(action, ast.Constant) and isinstance(action.value, str), path
            actions.add(action.value)

    assert actions == {
        "change_pin",
        "delete_gmail_data",
        "disable_embedding_classification",
        "download_local_ai_model",
        "benchmark_local_ai_model",
        "enable_embedding_classification",
        "enable_developer_mode",
        "enable_network_access",
        "reset_all_data",
        "reset_classification_memory",
        "unlock",
    }
