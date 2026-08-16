from __future__ import annotations

import threading
import time
from datetime import timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.core import background_jobs
from app.core import database as database_module
from app.core.background_jobs import (
    JobExecutionError,
    JobQueueFull,
    enqueue_job,
    latest_job,
    recover_expired_jobs,
    register_job_handler,
    request_job_cancel,
)
from app.core.time import utcnow_naive
from app.models.background_job import BackgroundJob


@pytest.fixture
def job_runtime(monkeypatch, db_engine):
    session_factory = sessionmaker(bind=db_engine, expire_on_commit=False)
    background_jobs.stop_background_job_worker(timeout=0)
    with background_jobs._handlers_lock:
        saved_handlers = dict(background_jobs._handlers)
        background_jobs._handlers.clear()
    monkeypatch.setattr(database_module, "SessionLocal", session_factory)
    background_jobs._worker_stop.clear()
    background_jobs._worker_wake.clear()
    background_jobs._worker_id = "test-worker"
    yield session_factory
    background_jobs.stop_background_job_worker(timeout=2)
    with background_jobs._handlers_lock:
        background_jobs._handlers.clear()
        background_jobs._handlers.update(saved_handlers)
    background_jobs._worker_stop.clear()


def _job(session_factory, job_id: str) -> BackgroundJob:
    db = session_factory()
    try:
        return db.query(BackgroundJob).filter_by(id=job_id).one()
    finally:
        db.close()


def test_active_key_is_atomic_across_simultaneous_enqueues(job_runtime):
    barrier = threading.Barrier(3)
    results = []
    errors = []

    def enqueue():
        barrier.wait()
        try:
            results.append(
                enqueue_job("test_atomic", active_key="one-at-a-time")
            )
        except Exception as exc:  # pragma: no cover - asserted below
            errors.append(exc)

    threads = [threading.Thread(target=enqueue) for _ in range(2)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join(timeout=5)

    assert errors == []
    assert sum(result.created for result in results) == 1
    assert len({result.job_id for result in results}) == 1


def test_latest_job_does_not_cross_shared_active_key_kinds(job_runtime):
    first = enqueue_job("test_first_kind", active_key="shared-key")

    assert latest_job(
        kind="test_second_kind",
        active_key="shared-key",
    ) is None
    assert latest_job(
        kind="test_first_kind",
        active_key="shared-key",
    )["id"] == first.job_id


def test_queue_applies_backpressure_before_unbounded_growth(job_runtime, monkeypatch):
    monkeypatch.setattr(background_jobs, "MAX_PENDING_JOBS", 1)
    enqueue_job("test_first", active_key="first")
    with pytest.raises(JobQueueFull):
        enqueue_job("test_second", active_key="second")


def test_enqueue_retries_a_short_database_write_lock(job_runtime):
    locker = job_runtime()
    locker.execute(text("BEGIN IMMEDIATE"))
    result = []
    errors = []

    def enqueue():
        try:
            result.append(enqueue_job("test_lock", active_key="database-lock"))
        except Exception as exc:  # pragma: no cover - asserted below
            errors.append(exc)

    thread = threading.Thread(target=enqueue)
    thread.start()
    time.sleep(0.08)
    locker.commit()
    locker.close()
    thread.join(timeout=5)

    assert errors == []
    assert result[0].created is True


def test_claim_execute_and_terminal_result_release_the_active_key(job_runtime):
    register_job_handler(
        "test_success",
        lambda context, payload: {
            "value": payload["value"],
            "job": context.job_id,
        },
    )
    queued = enqueue_job(
        "test_success",
        payload={"value": 7},
        active_key="successful-work",
    )

    claimed = background_jobs._claim_next_job()
    assert claimed == queued.job_id
    background_jobs._execute_job(claimed)

    completed = _job(job_runtime, queued.job_id)
    assert completed.status == "completed"
    assert completed.progress == 100
    assert completed.active_key is None
    assert completed.result_json


def test_running_job_honours_durable_cancellation(job_runtime):
    calls = []
    register_job_handler(
        "test_cancel",
        lambda _context, _payload: calls.append("ran") or {},
    )
    queued = enqueue_job("test_cancel", active_key="cancel-work")
    claimed = background_jobs._claim_next_job()
    assert claimed == queued.job_id
    assert request_job_cancel(queued.job_id) is True

    background_jobs._execute_job(claimed)

    cancelled = _job(job_runtime, queued.job_id)
    assert cancelled.status == "cancelled"
    assert cancelled.active_key is None
    assert calls == []
    assert request_job_cancel(queued.job_id) is False


def test_retry_backoff_becomes_poisoned_after_bounded_attempts(job_runtime):
    def fail(_context, _payload):
        raise JobExecutionError("SYNTHETIC_RETRY", retryable=True)

    register_job_handler("test_retry", fail)
    queued = enqueue_job(
        "test_retry",
        active_key="retry-work",
        max_attempts=2,
    )

    for expected_attempt in (1, 2):
        claimed = background_jobs._claim_next_job()
        assert claimed == queued.job_id
        background_jobs._execute_job(claimed)
        state = _job(job_runtime, queued.job_id)
        assert state.attempt == expected_attempt
        if expected_attempt == 1:
            assert state.status == "retry_wait"
            assert state.available_at > utcnow_naive()
            db = job_runtime()
            try:
                stored = db.query(BackgroundJob).filter_by(id=queued.job_id).one()
                stored.available_at = utcnow_naive() - timedelta(seconds=1)
                db.commit()
            finally:
                db.close()
        else:
            assert state.status == "poisoned"
            assert state.failure_code == "SYNTHETIC_RETRY"
            assert state.active_key is None


def test_expired_crash_lease_is_recovered_without_duplicate_execution(job_runtime):
    queued = enqueue_job(
        "test_crash",
        active_key="crash-work",
        max_attempts=2,
    )
    assert background_jobs._claim_next_job() == queued.job_id
    db = job_runtime()
    try:
        stored = db.query(BackgroundJob).filter_by(id=queued.job_id).one()
        stored.lease_expires_at = utcnow_naive() - timedelta(seconds=1)
        db.commit()
    finally:
        db.close()

    assert recover_expired_jobs() == 1
    recovered = _job(job_runtime, queued.job_id)
    assert recovered.status == "retry_wait"
    assert recovered.attempt == 1
    assert recovered.failure_code == "JOB_LEASE_EXPIRED"
    assert recovered.active_key == "crash-work"


def test_dispatcher_never_runs_more_than_the_configured_concurrency(job_runtime):
    active = 0
    maximum = 0
    lock = threading.Lock()
    two_started = threading.Event()
    release = threading.Event()

    def handler(_context, _payload):
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
            if active == background_jobs.MAX_CONCURRENT_JOBS:
                two_started.set()
        assert release.wait(timeout=5)
        with lock:
            active -= 1
        return {}

    register_job_handler("test_bounded", handler)
    queued = [
        enqueue_job("test_bounded", active_key=f"bounded-{index}")
        for index in range(3)
    ]
    background_jobs.start_background_job_worker()
    assert two_started.wait(timeout=5)
    assert maximum == background_jobs.MAX_CONCURRENT_JOBS
    states = [_job(job_runtime, item.job_id).status for item in queued]
    assert states.count("running") == 2
    assert states.count("queued") == 1
    release.set()

    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if all(_job(job_runtime, item.job_id).status == "completed" for item in queued):
            break
        time.sleep(0.02)
    else:
        raise AssertionError("bounded worker did not finish queued work")


def test_claimed_job_waits_out_a_short_sqlite_read_lock(job_runtime):
    calls = []
    register_job_handler(
        "test_claim_read_lock",
        lambda _context, _payload: calls.append("ran") or {},
    )
    queued = enqueue_job("test_claim_read_lock", active_key="claim-read-lock")
    assert background_jobs._claim_next_job() == queued.job_id

    locker = job_runtime()
    locker.execute(text("BEGIN IMMEDIATE"))
    locker.execute(
        text(
            "UPDATE background_jobs SET public_message = public_message "
            "WHERE id = :job_id"
        ),
        {"job_id": queued.job_id},
    )
    worker = threading.Thread(
        target=background_jobs._execute_job,
        args=(queued.job_id,),
    )
    worker.start()
    time.sleep(0.08)
    locker.commit()
    locker.close()
    worker.join(timeout=5)

    assert worker.is_alive() is False
    assert calls == ["ran"]
    assert _job(job_runtime, queued.job_id).status == "completed"
