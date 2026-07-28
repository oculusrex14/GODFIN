from __future__ import annotations

from datetime import timedelta

from app.core.auth import hash_token
from app.core.time import utcnow_naive
from app.models.pin_attempt import PinAttempt
from app.models.session import AuthSession


def test_auth_status_first_run(client):
    resp = client.get("/api/v1/auth/status")
    assert resp.status_code == 200
    assert resp.json()["is_first_run"] is True


def test_set_pin(client):
    resp = client.post("/api/v1/auth/set-pin", json={"pin": "1234"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["authenticated"] is True
    assert data["token"] is not None


def test_set_pin_invalid_format(client):
    resp = client.post("/api/v1/auth/set-pin", json={"pin": "abc"})
    assert resp.status_code == 422


def test_set_pin_only_once(client):
    client.post("/api/v1/auth/set-pin", json={"pin": "1234"})
    resp = client.post("/api/v1/auth/set-pin", json={"pin": "5678"})
    assert resp.status_code == 400


def test_verify_pin_correct(client):
    client.post("/api/v1/auth/set-pin", json={"pin": "1234"})
    resp = client.post("/api/v1/auth/verify-pin", json={"pin": "1234"})
    assert resp.status_code == 200
    assert resp.json()["authenticated"] is True
    assert resp.json()["token"] is not None


def test_verify_pin_wrong(client):
    client.post("/api/v1/auth/set-pin", json={"pin": "1234"})
    # Use a non-weak PIN ( avoids 400 from format validation)
    resp = client.post("/api/v1/auth/verify-pin", json={"pin": "9876"})
    assert resp.status_code == 401


def test_change_pin(auth_client):
    resp = auth_client.post(
        "/api/v1/auth/change-pin",
        json={"current_pin": "1234", "new_pin": "9876"},
    )
    assert resp.status_code == 200
    assert resp.json()["authenticated"] is True
    # Verify new PIN works
    resp2 = auth_client.post("/api/v1/auth/verify-pin", json={"pin": "9876"})
    assert resp2.status_code == 200


def test_change_pin_wrong_current(auth_client):
    resp = auth_client.post(
        "/api/v1/auth/change-pin",
        json={"current_pin": "9876", "new_pin": "5678"},
    )
    assert resp.status_code == 400


def test_change_pin_requires_auth(client):
    resp = client.post(
        "/api/v1/auth/change-pin",
        json={"current_pin": "1234", "new_pin": "9876"},
    )
    assert resp.status_code == 401


def test_logout(auth_client, db_session):
    token = auth_client.headers["Authorization"].removeprefix("Bearer ")
    resp = auth_client.post("/api/v1/auth/logout")
    assert resp.status_code == 200
    assert resp.json()["status"] == "logged_out"
    assert db_session.query(AuthSession).filter_by(token_hash=hash_token(token)).first() is None


def test_sessions_are_hashed_and_capped_at_three(client, db_session):
    first = client.post("/api/v1/auth/set-pin", json={"pin": "1234"}).json()["token"]
    issued = [first]
    for _ in range(3):
        issued.append(
            client.post("/api/v1/auth/verify-pin", json={"pin": "1234"}).json()["token"]
        )

    sessions = db_session.query(AuthSession).order_by(AuthSession.created_at).all()
    assert len(sessions) == 3
    persisted_hashes = {session.token_hash for session in sessions}
    assert all(token not in persisted_hashes for token in issued)
    assert hash_token(first) not in persisted_hashes
    assert hash_token(issued[-1]) in persisted_hashes


def test_expired_session_is_rejected(client, db_session):
    token = client.post("/api/v1/auth/set-pin", json={"pin": "1234"}).json()["token"]
    session = db_session.query(AuthSession).filter_by(token_hash=hash_token(token)).one()
    session.expires_at = utcnow_naive() - timedelta(seconds=1)
    db_session.commit()

    response = client.get(
        "/api/v1/settings",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401
    assert db_session.query(AuthSession).filter_by(token_hash=hash_token(token)).first() is None


def test_pin_rate_limit_persists_in_database(client, db_session):
    client.post("/api/v1/auth/set-pin", json={"pin": "1234"})
    for _ in range(5):
        response = client.post("/api/v1/auth/verify-pin", json={"pin": "9876"})
        assert response.status_code == 401

    attempt = db_session.query(PinAttempt).filter_by(client_ip="testclient").one()
    assert attempt.failed_attempts == 5
    assert attempt.blocked_until is not None

    blocked = client.post("/api/v1/auth/verify-pin", json={"pin": "1234"})
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) > 0


def test_untrusted_forwarded_for_is_ignored(client, db_session):
    client.post("/api/v1/auth/set-pin", json={"pin": "1234"})
    client.post(
        "/api/v1/auth/verify-pin",
        json={"pin": "9876"},
        headers={"X-Forwarded-For": "203.0.113.50"},
    )
    assert db_session.query(PinAttempt).filter_by(client_ip="testclient").count() == 1
    assert db_session.query(PinAttempt).filter_by(client_ip="203.0.113.50").count() == 0
