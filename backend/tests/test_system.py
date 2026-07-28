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
