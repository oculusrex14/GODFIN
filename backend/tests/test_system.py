from __future__ import annotations

from app.models.app_setting import AppSetting


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
    from datetime import UTC, datetime

    from app.models.app_setting import AppSetting

    for key, value in {
        "license_tier": "pro",
        "license_status": "active",
        "license_verified_at": datetime.now(UTC).isoformat(),
    }.items():
        db_session.query(AppSetting).filter_by(key=key).one().value = value
    db_session.commit()

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

    response = auth_client.post("/api/v1/system/embeddings/enable")
    assert response.status_code == 202
    assert response.json()["started"] is True
    assert response.json()["status"] == "queued"

    setting = db_session.query(AppSetting).filter_by(key="enable_embeddings").one()
    db_session.refresh(setting)
    assert setting.value == "true"


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
