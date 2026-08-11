from __future__ import annotations

from app.models.app_setting import AppSetting
from tests.license_helpers import install_test_license


def test_embeddings_disabled_by_default(auth_client):
    response = auth_client.get("/api/v1/system/embeddings/status")
    assert response.status_code == 200
    assert response.json() == {
        "enabled": False,
        "status": "disabled",
        "progress": 0,
        "message": "Embedding classification is disabled.",
        "updated": 0,
        "total": 0,
    }


def test_enable_embeddings_starts_on_demand(auth_client, db_session, monkeypatch):
    install_test_license(db_session, "pro")

    monkeypatch.setattr(
        "app.core.embedding_service.start_embedding_setup",
        lambda: True,
    )
    monkeypatch.setattr(
        "app.core.embedding_service.get_embedding_setup_status",
        lambda: {
            "status": "queued",
            "progress": 1,
            "message": "Preparing the local embedding model…",
            "updated": 0,
            "total": 0,
        },
    )

    response = auth_client.post(
        "/api/v1/system/embeddings/enable",
        json={"confirmed": True, "current_pin": "4826"},
    )
    assert response.status_code == 202
    assert response.json()["started"] is True
    assert response.json()["status"] == "queued"

    setting = db_session.query(AppSetting).filter_by(key="enable_embeddings").one()
    db_session.refresh(setting)
    assert setting.value == "true"


def _activate_pro(db_session):
    install_test_license(db_session, "pro")


def test_embedding_setup_requires_explicit_approval_and_current_pin(
    auth_client,
    db_session,
    monkeypatch,
):
    _activate_pro(db_session)
    started = []
    monkeypatch.setattr(
        "app.core.embedding_service.start_embedding_setup",
        lambda: started.append(True) or True,
    )

    missing_approval = auth_client.post(
        "/api/v1/system/embeddings/enable",
        json={"current_pin": "4826"},
    )
    missing_pin = auth_client.post(
        "/api/v1/system/embeddings/enable",
        json={"confirmed": True},
    )
    wrong_pin = auth_client.post(
        "/api/v1/system/embeddings/enable",
        json={"confirmed": True, "current_pin": "0000"},
    )

    assert missing_approval.status_code == 422
    assert missing_pin.status_code == 403
    assert wrong_pin.status_code == 403
    assert started == []


def test_embedding_enable_is_single_flight_and_disable_cancels(
    auth_client,
    db_session,
    monkeypatch,
):
    _activate_pro(db_session)
    monkeypatch.setattr(
        "app.core.embedding_service.start_embedding_setup",
        lambda: False,
    )
    monkeypatch.setattr(
        "app.core.embedding_service.get_embedding_setup_status",
        lambda: {
            "status": "indexing",
            "progress": 40,
            "message": "Indexing merchant memory locally…",
            "updated": 4,
            "total": 10,
        },
    )
    monkeypatch.setattr(
        "app.core.embedding_service.cancel_embedding_setup",
        lambda: True,
    )

    repeated = auth_client.post(
        "/api/v1/system/embeddings/enable",
        json={"confirmed": True, "current_pin": "4826"},
    )
    disabled = auth_client.post(
        "/api/v1/system/embeddings/disable",
        json={"confirmed": True, "current_pin": "4826"},
    )

    assert repeated.status_code == 202
    assert repeated.json()["started"] is False
    assert repeated.json()["status"] == "indexing"
    assert disabled.status_code == 200
    assert disabled.json()["cancel_requested"] is True
    setting = db_session.query(AppSetting).filter_by(key="enable_embeddings").one()
    db_session.refresh(setting)
    assert setting.value == "false"


def test_unsafe_script_and_unbounded_maintenance_routes_are_not_exposed(auth_client):
    from pathlib import Path

    for route in (
        "/api/v1/system/restart",
        "/api/v1/system/backfill-embeddings",
        "/api/v1/system/apply-confidence-decay",
    ):
        response = auth_client.post(route)
        assert response.status_code == 404
    assert not (Path(__file__).parents[1] / "restart.sh").exists()


def test_local_ai_actions_require_current_pin(auth_client, monkeypatch):
    pull_calls = []
    benchmark_calls = []
    monkeypatch.setattr(
        "app.core.local_ai.start_model_pull",
        lambda model, confirmed: pull_calls.append((model, confirmed)),
    )
    monkeypatch.setattr(
        "app.core.local_ai.benchmark_model",
        lambda model: benchmark_calls.append(model),
    )

    download = auth_client.post(
        "/api/v1/system/local-ai/download",
        json={"model": "qwen3:4b", "confirmed": True},
    )
    benchmark = auth_client.post(
        "/api/v1/system/local-ai/benchmark",
        json={"model": "qwen3:4b", "confirmed": True},
    )

    assert download.status_code == 403
    assert benchmark.status_code == 403
    assert pull_calls == []
    assert benchmark_calls == []


def test_embedding_setup_cancel_is_idempotent_and_work_is_bounded():
    from app.core import embedding_service

    original = embedding_service.get_embedding_setup_status()
    try:
        embedding_service._setup_cancel.clear()
        embedding_service._set_setup_status(
            status="indexing",
            progress=50,
            message="Indexing merchant memory locally…",
            updated=5,
            total=10,
        )
        assert embedding_service.cancel_embedding_setup() is True
        assert embedding_service.get_embedding_setup_status()["status"] == "cancelling"
        assert embedding_service.cancel_embedding_setup() is False
        assert embedding_service.MAX_SETUP_MERCHANTS == 5_000
    finally:
        embedding_service._setup_cancel.clear()
        embedding_service._set_setup_status(**original)


def test_embedding_setup_does_not_return_raw_worker_errors(monkeypatch):
    import time

    from app.core import embedding_service

    original = embedding_service.get_embedding_setup_status()
    try:
        embedding_service._set_setup_status(status="idle")

        def fail_model_load():
            raise RuntimeError("/Users/private/financial/model-cache")

        monkeypatch.setattr(embedding_service, "_get_model", fail_model_load)
        assert embedding_service.start_embedding_setup() is True
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            status = embedding_service.get_embedding_setup_status()
            if status["status"] == "failed":
                break
            time.sleep(0.01)
        else:
            raise AssertionError("embedding setup worker did not finish")

        assert status["message"].startswith("Matching setup could not finish")
        assert "/Users/" not in status["message"]
    finally:
        embedding_service._setup_cancel.clear()
        embedding_service._set_setup_status(**original)


def test_support_diagnostics_include_backup_health_without_sensitive_state(
    auth_client,
    db_session,
):
    values = {
        "backup_scheduler_status": "operational",
        "backup_job_status": "degraded",
        "backup_last_success_at": "2026-08-10T18:29:00+00:00",
        "backup_job_last_failure_at": "2026-08-11T01:00:00+00:00",
        "backup_job_next_retry_at": "2026-08-11T01:01:00+00:00",
        "backup_job_failure_code": "automatic_backup_failed",
        "backup_job_failure_count": "2",
        "backup_last_filename": "godfin_backup_private_name.db",
        "backup_directory": "/Users/private/financial/backups",
        "gmail_access_token": "must-never-appear",
    }
    for key, value in values.items():
        db_session.merge(AppSetting(key=key, value=value))
    db_session.commit()

    response = auth_client.get("/api/v1/system/diagnostics")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-disposition"].endswith(
        "godfin-support-diagnostics.json"
    )
    diagnostics = response.json()
    assert diagnostics["application"]["api_status"] == "operational"
    assert diagnostics["backup_protection"] == {
        "status": "degraded",
        "scheduler_status": "operational",
        "job_status": "degraded",
        "last_success_at": "2026-08-10T18:29:00+00:00",
        "last_failure_at": "2026-08-11T01:00:00+00:00",
        "next_retry_at": "2026-08-11T01:01:00+00:00",
        "failure_code": "automatic_backup_failed",
        "failure_count": 2,
    }
    serialized = response.text
    assert "private" not in serialized
    assert "financial" not in serialized
    assert "must-never-appear" not in serialized
