from __future__ import annotations


def test_health_endpoint(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "alive"
    assert data["liveness"] is True
    assert data["database"] == "not_checked"
    assert data["version"] == "0.1.0"


def test_readiness_endpoint_reports_critical_and_optional_dependencies(client):
    response = client.get("/api/v1/ready")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    data = response.json()
    assert data["ready"] is True
    assert data["dependencies"]["database"] == "connected"
    assert data["dependencies"]["lifecycle"] == "test"
    assert data["dependencies"]["schema"] == "unknown"
    assert data["background_jobs"]["active"] == 0
