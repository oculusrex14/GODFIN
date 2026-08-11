from __future__ import annotations

import json
import logging
import sys
from types import SimpleNamespace

from sqlalchemy.orm import sessionmaker

from app.api.v1.endpoints.health import readiness_snapshot
from app.core import background_jobs
from app.core import database as database_module
from app.core.local_metrics import (
    request_metrics_snapshot,
    reset_request_metrics_for_test,
)
from app.core.logging_config import JSONFormatter, setup_logging
from app.core.request_context import _request_id
from app.models.background_job import BackgroundJob


def test_structured_logs_redact_credentials_identifiers_and_private_paths():
    try:
        raise RuntimeError(
            "Bearer secret-token-123456 at /Users/private/finance/file.pdf"
        )
    except RuntimeError:
        exc_info = sys.exc_info()
    record = logging.LogRecord(
        name="godfin.test",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg=(
            "authorization=Bearer abcdefghijklmnop "
            "password=hunter2 owner@example.com +919876543210 "
            "/Users/owner/GODFIN/private.db"
        ),
        args=(),
        exc_info=exc_info,
    )
    record.request_id = "a" * 32
    payload = json.loads(JSONFormatter().format(record))
    serialized = json.dumps(payload)

    for secret in (
        "abcdefghijklmnop",
        "hunter2",
        "owner@example.com",
        "9876543210",
        "/Users/private",
        "/Users/owner",
    ):
        assert secret not in serialized
    assert payload["request_id"] == "a" * 32
    assert payload["exception_type"] == "RuntimeError"
    assert "<redacted>" in serialized
    assert "<local-path>" in serialized


def test_logging_setup_is_idempotent_and_uses_private_file_permissions(tmp_path):
    root = logging.getLogger()
    before = list(root.handlers)
    try:
        setup_logging(tmp_path)
        setup_logging(tmp_path)
        godfin_handlers = [
            handler
            for handler in root.handlers
            if getattr(handler, "_godfin_handler", False)
        ]
        assert len(godfin_handlers) == 2
        log_file = tmp_path / "godfin.log"
        assert log_file.exists()
        assert log_file.stat().st_mode & 0o077 == 0
    finally:
        for handler in list(root.handlers):
            if getattr(handler, "_godfin_handler", False):
                root.removeHandler(handler)
                handler.close()
        for handler in before:
            if handler not in root.handlers:
                root.addHandler(handler)


def test_request_metrics_are_bounded_aggregates_without_raw_paths(client):
    reset_request_metrics_for_test()
    assert client.get("/api/v1/health?token=must-not-appear").status_code == 200
    assert client.get("/api/v1/ready").status_code == 200

    snapshot = request_metrics_snapshot()
    assert snapshot["request_count"] == 2
    assert snapshot["remote_telemetry"] is False
    assert snapshot["retention"] == "process_lifetime_aggregate_only"
    serialized = json.dumps(snapshot)
    assert "must-not-appear" not in serialized
    assert "token=" not in serialized
    assert all("/api/" not in key for key in snapshot["operations"])


def test_background_job_inherits_only_the_random_request_correlation(
    monkeypatch,
    db_engine,
):
    session_factory = sessionmaker(bind=db_engine, expire_on_commit=False)
    monkeypatch.setattr(database_module, "SessionLocal", session_factory)
    token = _request_id.set("b" * 32)
    try:
        queued = background_jobs.enqueue_job(
            "test_correlation",
            active_key="correlated-work",
        )
    finally:
        _request_id.reset(token)
    db = session_factory()
    try:
        stored = db.query(BackgroundJob).filter_by(id=queued.job_id).one()
        assert stored.correlation_id == "b" * 32
        assert "token" not in stored.payload_json
    finally:
        db.close()


def test_readiness_fails_closed_when_the_database_is_unavailable():
    class BrokenDatabase:
        def execute(self, *_args, **_kwargs):
            raise RuntimeError("database unavailable")

        def rollback(self):
            return None

        def query(self, *_args, **_kwargs):
            raise RuntimeError("database unavailable")

    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                lifecycle_status="ready",
                scheduler_status="ready",
                job_worker_status="ready",
            )
        )
    )
    payload = readiness_snapshot(request, BrokenDatabase())
    assert payload["ready"] is False
    assert payload["status"] == "unavailable"
    assert payload["dependencies"]["database"] == "unavailable"
