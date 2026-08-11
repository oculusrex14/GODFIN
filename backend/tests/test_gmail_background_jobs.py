from __future__ import annotations

from sqlalchemy.orm import sessionmaker

from app.core import database as database_module
from app.core.gmail_service import GmailFetchResult
from app.core.background_jobs import EnqueueResult
from app.core.ingestion import run_scheduled_ingestion_background


def test_gmail_background_routes_enqueue_one_durable_single_flight_job(
    auth_client,
    monkeypatch,
):
    calls = []

    def enqueue(kind, **options):
        calls.append((kind, options))
        return EnqueueResult(
            job_id=f"job-{len(calls)}",
            created=True,
            status="queued",
        )

    monkeypatch.setattr(
        "app.api.v1.endpoints.gmail.is_connected",
        lambda: True,
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.gmail.enqueue_job",
        enqueue,
    )

    initial = auth_client.post("/api/v1/ingest/gmail/initial/start")
    ranged = auth_client.post(
        "/api/v1/ingest/gmail/range/start",
        json={"start_date": "2026-01-01", "end_date": "2026-01-31"},
    )

    assert initial.status_code == 200
    assert initial.json()["started"] is True
    assert initial.json()["job_id"] == "job-1"
    assert ranged.status_code == 200
    assert ranged.json()["started"] is True
    assert ranged.json()["job_id"] == "job-2"
    assert calls == [
        (
            "gmail_initial_sync",
            {
                "active_key": "gmail-ingestion",
                "max_attempts": 3,
                "public_message": "Preparing the first Gmail import…",
            },
        ),
        (
            "gmail_date_range",
            {
                "payload": {
                    "start_date": "2026-01-01",
                    "end_date": "2026-02-01",
                },
                "active_key": "gmail-ingestion",
                "max_attempts": 3,
                "public_message": "Preparing the selected Gmail date range…",
            },
        ),
    ]


def test_gmail_background_status_and_cancellation_are_job_backed(
    auth_client,
    monkeypatch,
):
    job = {
        "id": "durable-job",
        "kind": "gmail_initial_sync",
        "status": "running",
        "progress": 37,
        "total": 120,
        "message": "Importing Gmail messages…",
        "failure_code": None,
        "attempt": 1,
        "max_attempts": 3,
        "retry_at": None,
        "result": None,
        "cancel_requested": False,
    }
    cancelled = []
    monkeypatch.setattr(
        "app.api.v1.endpoints.gmail.latest_job",
        lambda **_kwargs: job,
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.gmail.request_job_cancel",
        lambda job_id: cancelled.append(job_id) or True,
    )

    status = auth_client.get("/api/v1/ingest/gmail/sync-status")
    cancel = auth_client.post("/api/v1/ingest/gmail/sync/cancel")

    assert status.status_code == 200
    assert status.json()["status"] == "running"
    assert status.json()["percent"] == 37
    assert status.json()["total"] == 120
    assert status.json()["job_id"] == "durable-job"
    assert cancel.status_code == 200
    assert cancel.json() == {
        "cancel_requested": True,
        "job_id": "durable-job",
    }
    assert cancelled == ["durable-job"]


def test_scheduled_fetch_does_not_hold_a_sqlite_transaction(
    db_engine,
    monkeypatch,
):
    Session = sessionmaker(bind=db_engine)
    opened_sessions = []

    def session_factory():
        session = Session()
        opened_sessions.append(session)
        return session

    def fetch_messages(**_options):
        assert opened_sessions
        assert all(not session.in_transaction() for session in opened_sessions)
        return GmailFetchResult(
            messages=[],
            history_id="synthetic-history",
            status="empty",
        )

    monkeypatch.setattr(database_module, "SessionLocal", session_factory)
    monkeypatch.setattr(
        "app.core.ingestion.fetch_messages",
        fetch_messages,
    )

    result = run_scheduled_ingestion_background()

    assert result["processed"] == 0
    assert result["created"] == 0
    assert len(opened_sessions) == 2
