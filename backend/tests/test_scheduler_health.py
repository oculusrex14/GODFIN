from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import sessionmaker

from app.core import backup as backup_module
from app.core import background_jobs
from app.core import database as database_module
from app.core import job_handlers
from app.core import scheduler as scheduler_module
from app.models.app_setting import AppSetting
from app.models.background_job import BackgroundJob


class _FakeTimer:
    created: list["_FakeTimer"] = []

    def __init__(self, interval, function):
        self.interval = interval
        self.function = function
        self.daemon = False
        self._alive = False
        self.created.append(self)

    def start(self):
        self._alive = True

    def cancel(self):
        self._alive = False

    def is_alive(self):
        return self._alive

    def fire(self):
        self._alive = False
        self.function()


class _FakeScheduler:
    def __init__(self, start_failures=0):
        self.running = False
        self.jobs = {}
        self.start_failures = start_failures

    def add_job(self, function, _trigger, **options):
        self.jobs[options["id"]] = function

    def get_job(self, job_id):
        return self.jobs.get(job_id)

    def remove_job(self, job_id):
        self.jobs.pop(job_id, None)

    def start(self):
        if self.start_failures:
            self.start_failures -= 1
            raise RuntimeError("synthetic scheduler start failure")
        self.running = True

    def shutdown(self, wait=False):
        self.running = False


def _settings(session_factory) -> dict[str, str]:
    db = session_factory()
    try:
        return {setting.key: setting.value for setting in db.query(AppSetting).all()}
    finally:
        db.close()


@pytest.fixture
def scheduler_runtime(monkeypatch, db_engine):
    session_factory = sessionmaker(bind=db_engine)
    background_jobs.stop_background_job_worker(timeout=0)
    with background_jobs._handlers_lock:
        saved_handlers = dict(background_jobs._handlers)
        background_jobs._handlers.clear()
    monkeypatch.setattr(database_module, "SessionLocal", session_factory)
    monkeypatch.setattr(scheduler_module.threading, "Timer", _FakeTimer)
    monkeypatch.setattr(scheduler_module.random, "uniform", lambda *_args: 0.0)
    _FakeTimer.created.clear()
    scheduler_module._scheduler = None
    scheduler_module._scheduler_retry_timer = None
    scheduler_module._backup_retry_timer = None
    scheduler_module._scheduler_retry_attempts = 0
    scheduler_module._backup_retry_attempts = 0
    scheduler_module._shutdown_requested = False
    background_jobs._worker_stop.clear()
    background_jobs._worker_id = "scheduler-test-worker"
    background_jobs.register_job_handler(
        "automatic_backup",
        job_handlers._automatic_backup,
    )
    yield session_factory
    scheduler_module.stop_scheduler()
    scheduler_module._scheduler = None
    background_jobs.stop_background_job_worker(timeout=0)
    with background_jobs._handlers_lock:
        background_jobs._handlers.clear()
        background_jobs._handlers.update(saved_handlers)
    background_jobs._worker_stop.clear()


def test_scheduler_start_failure_is_persistent_and_has_one_bounded_retry(
    scheduler_runtime,
):
    scheduler_module.schedule_scheduler_recovery(
        "/tmp/synthetic-godfin.db",
        "/tmp/synthetic-backups",
    )
    scheduler_module.schedule_scheduler_recovery(
        "/tmp/synthetic-godfin.db",
        "/tmp/synthetic-backups",
    )

    values = _settings(scheduler_runtime)
    assert values["backup_scheduler_status"] == "degraded"
    assert values["backup_scheduler_failure_code"] == "scheduler_start_failed"
    assert values["backup_scheduler_failure_count"] == "1"
    assert datetime.fromisoformat(values["backup_scheduler_next_retry_at"]).tzinfo
    assert len(_FakeTimer.created) == 1
    assert _FakeTimer.created[0].is_alive()
    assert _FakeTimer.created[0].interval == 30.0


def test_failed_automatic_backup_preserves_last_success_and_recovers_on_retry(
    scheduler_runtime,
    monkeypatch,
):
    db = scheduler_runtime()
    db.add(
        AppSetting(
            key="backup_last_success_at",
            value="2026-08-01T23:59:00+00:00",
        )
    )
    db.commit()
    db.close()

    outcomes = [RuntimeError("synthetic permission failure"), "godfin_backup_ok.db"]

    def create_backup(_db_path, _backup_dir):
        result = outcomes.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(backup_module, "create_backup", create_backup)
    fake_scheduler = _FakeScheduler()
    monkeypatch.setattr(scheduler_module, "_get_scheduler", lambda: fake_scheduler)

    assert scheduler_module.start_scheduler(
        "/tmp/synthetic-godfin.db",
        "/tmp/synthetic-backups",
    ) is True
    fake_scheduler.jobs["nightly_batch"]()
    claimed = background_jobs._claim_next_job()
    assert claimed is not None
    background_jobs._execute_job(claimed)

    failed = _settings(scheduler_runtime)
    assert failed["backup_job_status"] == "degraded"
    assert failed["backup_job_failure_code"] == "automatic_backup_failed"
    assert failed["backup_job_failure_count"] == "1"
    assert failed["backup_last_success_at"] == "2026-08-01T23:59:00+00:00"
    assert len(_FakeTimer.created) == 0
    db = scheduler_runtime()
    try:
        job = db.query(BackgroundJob).filter_by(id=claimed).one()
        assert job.status == "retry_wait"
        job.available_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.commit()
    finally:
        db.close()
    assert background_jobs._claim_next_job() == claimed
    background_jobs._execute_job(claimed)
    recovered = _settings(scheduler_runtime)
    assert recovered["backup_job_status"] == "ok"
    assert recovered["backup_job_failure_code"] == ""
    assert recovered["backup_job_failure_count"] == "0"
    assert recovered["backup_last_filename"] == "godfin_backup_ok.db"
    assert recovered["backup_last_success_at"] != "2026-08-01T23:59:00+00:00"
    assert datetime.fromisoformat(recovered["backup_last_success_at"]).tzinfo is timezone.utc


def test_scheduler_recovery_clears_degraded_state_without_reinstall(
    scheduler_runtime,
    monkeypatch,
):
    scheduler_module.schedule_scheduler_recovery(
        "/tmp/synthetic-godfin.db",
        "/tmp/synthetic-backups",
    )
    fake_scheduler = _FakeScheduler()
    monkeypatch.setattr(scheduler_module, "_get_scheduler", lambda: fake_scheduler)

    _FakeTimer.created[0].fire()

    values = _settings(scheduler_runtime)
    assert fake_scheduler.running is True
    assert values["backup_scheduler_status"] == "operational"
    assert values["backup_scheduler_failure_code"] == ""
    assert values["backup_scheduler_next_retry_at"] == ""
    assert values["backup_scheduler_failure_count"] == "0"


def test_scheduler_retry_failure_uses_bounded_backoff_without_a_storm(
    scheduler_runtime,
    monkeypatch,
):
    scheduler_module.schedule_scheduler_recovery(
        "/tmp/synthetic-godfin.db",
        "/tmp/synthetic-backups",
    )
    fake_scheduler = _FakeScheduler(start_failures=1)
    monkeypatch.setattr(scheduler_module, "_get_scheduler", lambda: fake_scheduler)

    _FakeTimer.created[0].fire()

    values = _settings(scheduler_runtime)
    assert values["backup_scheduler_status"] == "degraded"
    assert values["backup_scheduler_failure_count"] == "2"
    assert len(_FakeTimer.created) == 2
    assert _FakeTimer.created[1].is_alive()
    assert _FakeTimer.created[1].interval == 60.0


def test_persisted_backup_failure_retries_after_application_restart(
    scheduler_runtime,
    monkeypatch,
):
    db = scheduler_runtime()
    db.add(AppSetting(key="backup_job_status", value="degraded"))
    db.add(
        AppSetting(
            key="backup_job_failure_code",
            value="automatic_backup_failed",
        )
    )
    db.add(
        AppSetting(
            key="backup_job_last_failure_at",
            value="2026-08-02T00:01:00+00:00",
        )
    )
    db.add(
        AppSetting(
            key="backup_last_success_at",
            value="2026-08-01T23:59:00+00:00",
        )
    )
    db.commit()
    db.close()

    monkeypatch.setattr(
        backup_module,
        "create_backup",
        lambda *_args: "godfin_backup_recovered_after_restart.db",
    )
    fake_scheduler = _FakeScheduler()
    monkeypatch.setattr(scheduler_module, "_get_scheduler", lambda: fake_scheduler)

    assert scheduler_module.start_scheduler(
        "/tmp/synthetic-godfin.db",
        "/tmp/synthetic-backups",
    ) is True
    pending = _settings(scheduler_runtime)
    assert pending["backup_job_status"] == "degraded"
    assert pending["backup_job_failure_code"] == "automatic_backup_failed"
    assert pending["backup_job_last_failure_at"] == "2026-08-02T00:01:00+00:00"
    assert pending["backup_last_success_at"] == "2026-08-01T23:59:00+00:00"
    assert len(_FakeTimer.created) == 0
    claimed = background_jobs._claim_next_job()
    assert claimed is not None
    background_jobs._execute_job(claimed)
    recovered = _settings(scheduler_runtime)
    assert recovered["backup_job_status"] == "ok"
    assert recovered["backup_last_filename"] == "godfin_backup_recovered_after_restart.db"
