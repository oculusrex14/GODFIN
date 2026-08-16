"""SQLite-backed leases for bounded, restart-safe local background work."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable

from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError, OperationalError

from app.core.request_context import current_request_id
from app.core.time import utcnow_naive
from app.models.background_job import BackgroundJob

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = frozenset({"queued", "running", "retry_wait", "cancel_requested"})
TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled", "poisoned"})
MAX_PENDING_JOBS = 100
MAX_CONCURRENT_JOBS = 2
DEFAULT_LEASE_SECONDS = 120
DISPATCH_INTERVAL_SECONDS = 0.25
CANCELLATION_POLL_SECONDS = 0.5
MAX_PUBLIC_MESSAGE = 500
MAX_RESULT_BYTES = 32_000
_KIND_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{1,79}$")
_ACTIVE_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,159}$")

JobHandler = Callable[["JobContext", dict[str, Any]], dict[str, Any] | None]
_handlers: dict[str, JobHandler] = {}
_handlers_lock = threading.Lock()
_worker_lock = threading.Lock()
_worker_stop = threading.Event()
_worker_wake = threading.Event()
_dispatcher: threading.Thread | None = None
_worker_id = uuid.uuid4().hex
_active_threads: dict[str, threading.Thread] = {}


class JobQueueFull(RuntimeError):
    """Raised when bounded local backpressure rejects new work."""


class JobCancelled(RuntimeError):
    """Raised at a cooperative cancellation point."""


class JobExecutionError(RuntimeError):
    """A support-safe worker failure with an explicit retry policy."""

    def __init__(self, code: str, *, retryable: bool = True):
        super().__init__(code)
        self.code = _safe_code(code)
        self.retryable = retryable


@dataclass(frozen=True)
class EnqueueResult:
    job_id: str
    created: bool
    status: str


def _session():
    from app.core import database as database_module

    return database_module.SessionLocal()


def _safe_code(value: Any) -> str:
    normalized = re.sub(r"[^A-Z0-9_]+", "_", str(value or "JOB_FAILED").upper())
    return normalized.strip("_")[:80] or "JOB_FAILED"


def _safe_message(value: Any, fallback: str) -> str:
    text_value = " ".join(str(value or fallback).split())
    return text_value[:MAX_PUBLIC_MESSAGE]


def _encoded_json(value: dict[str, Any], *, limit: int) -> str:
    encoded = json.dumps(value, separators=(",", ":"), sort_keys=True)
    if len(encoded.encode("utf-8")) > limit:
        raise ValueError("Background-job metadata is too large")
    return encoded


def _decoded_json(value: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _retry_delay_seconds(job_id: str, attempt: int) -> float:
    base = min(300.0, 5.0 * (2 ** max(0, attempt - 1)))
    digest = hashlib.sha256(f"{job_id}:{attempt}".encode()).digest()
    jitter_ratio = int.from_bytes(digest[:2], "big") / 65535 * 0.2
    return base * (1 + jitter_ratio)


def _write_with_lock_retry(operation: Callable[[Any], Any]) -> Any:
    """Run one short SQLite mutation with bounded lock backoff."""
    for write_attempt in range(5):
        db = _session()
        try:
            result = operation(db)
            db.commit()
            return result
        except OperationalError as exc:
            db.rollback()
            if "locked" not in str(exc).lower():
                raise
            if write_attempt == 4:
                raise JobExecutionError("JOB_DATABASE_BUSY", retryable=True) from exc
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
        time.sleep(0.02 * (2**write_attempt))
    raise JobExecutionError("JOB_DATABASE_BUSY", retryable=True)


def register_job_handler(kind: str, handler: JobHandler) -> None:
    if not _KIND_PATTERN.fullmatch(kind):
        raise ValueError("Invalid background-job kind")
    with _handlers_lock:
        existing = _handlers.get(kind)
        if existing is not None and existing is not handler:
            raise RuntimeError(f"A handler is already registered for {kind}")
        _handlers[kind] = handler


def registered_job_kinds() -> tuple[str, ...]:
    with _handlers_lock:
        return tuple(sorted(_handlers))


def enqueue_job(
    kind: str,
    *,
    payload: dict[str, Any] | None = None,
    active_key: str,
    max_attempts: int = 3,
    public_message: str = "Work is waiting to start.",
) -> EnqueueResult:
    """Atomically deduplicate active work and apply bounded backpressure."""
    if not _KIND_PATTERN.fullmatch(kind):
        raise ValueError("Invalid background-job kind")
    if not _ACTIVE_KEY_PATTERN.fullmatch(active_key):
        raise ValueError("Invalid background-job active key")
    if max_attempts < 1 or max_attempts > 10:
        raise ValueError("Background-job attempts must be between 1 and 10")
    encoded_payload = _encoded_json(payload or {}, limit=MAX_RESULT_BYTES)
    for write_attempt in range(5):
        now = utcnow_naive()
        db = _session()
        try:
            db.execute(text("BEGIN IMMEDIATE"))
            existing = db.query(BackgroundJob).filter_by(
                active_key=active_key
            ).first()
            if existing is not None:
                result = EnqueueResult(existing.id, False, existing.status)
                db.commit()
                return result
            pending = db.query(BackgroundJob.id).filter(
                BackgroundJob.status.in_(ACTIVE_STATUSES)
            ).count()
            if pending >= MAX_PENDING_JOBS:
                db.rollback()
                raise JobQueueFull("The local background queue is full")
            job = BackgroundJob(
                kind=kind,
                active_key=active_key,
                payload_json=encoded_payload,
                status="queued",
                progress=0,
                total=0,
                public_message=_safe_message(
                    public_message,
                    "Work is waiting to start.",
                ),
                attempt=0,
                max_attempts=max_attempts,
                available_at=now,
                correlation_id=current_request_id(),
                created_at=now,
                updated_at=now,
            )
            db.add(job)
            db.flush()
            job_id = job.id
            db.commit()
            _worker_wake.set()
            return EnqueueResult(job_id, True, "queued")
        except IntegrityError:
            db.rollback()
            existing = db.query(BackgroundJob).filter_by(
                active_key=active_key
            ).first()
            if existing is None:
                raise
            return EnqueueResult(existing.id, False, existing.status)
        except OperationalError as exc:
            db.rollback()
            if "locked" not in str(exc).lower():
                raise
            if write_attempt == 4:
                raise JobQueueFull(
                    "The local background queue is temporarily busy"
                ) from exc
        finally:
            db.close()
        time.sleep(0.02 * (2**write_attempt))
    raise JobQueueFull("The local background queue is temporarily busy")


def _claim_next_job() -> str | None:
    now = utcnow_naive()
    lease_until = now + timedelta(seconds=DEFAULT_LEASE_SECONDS)
    db = _session()
    try:
        db.execute(text("BEGIN IMMEDIATE"))
        job = (
            db.query(BackgroundJob)
            .filter(
                BackgroundJob.status.in_(("queued", "retry_wait")),
                BackgroundJob.available_at <= now,
                BackgroundJob.cancel_requested.is_(False),
            )
            .order_by(BackgroundJob.available_at, BackgroundJob.created_at)
            .first()
        )
        if job is None:
            db.commit()
            return None
        job.status = "running"
        job.attempt += 1
        job.lease_owner = _worker_id
        job.lease_expires_at = lease_until
        job.started_at = job.started_at or now
        job.heartbeat_at = now
        job.updated_at = now
        db.commit()
        return job.id
    except OperationalError as exc:
        db.rollback()
        if "locked" not in str(exc).lower():
            raise
        return None
    finally:
        db.close()


def recover_expired_jobs() -> int:
    """Return abandoned leases to retry or poison them after bounded attempts."""
    now = utcnow_naive()
    recovered = 0
    db = _session()
    try:
        db.execute(text("BEGIN IMMEDIATE"))
        abandoned = db.query(BackgroundJob).filter(
            BackgroundJob.status.in_(("running", "cancel_requested")),
            BackgroundJob.lease_expires_at.isnot(None),
            BackgroundJob.lease_expires_at <= now,
        ).all()
        for job in abandoned:
            recovered += 1
            job.lease_owner = None
            job.lease_expires_at = None
            job.heartbeat_at = None
            job.updated_at = now
            if job.cancel_requested:
                _finish(job, "cancelled", now, "Work was cancelled.", None)
            elif job.attempt >= job.max_attempts:
                _finish(
                    job,
                    "poisoned",
                    now,
                    "Work stopped after repeated interrupted attempts.",
                    "JOB_LEASE_EXHAUSTED",
                )
            else:
                job.status = "retry_wait"
                job.available_at = now + timedelta(
                    seconds=_retry_delay_seconds(job.id, job.attempt)
                )
                job.public_message = "Interrupted work will retry safely."
                job.failure_code = "JOB_LEASE_EXPIRED"
        db.commit()
    finally:
        db.close()
    if recovered:
        _worker_wake.set()
    return recovered


def _finish(
    job: BackgroundJob,
    status: str,
    now: datetime,
    message: str,
    failure_code: str | None,
    *,
    result: dict[str, Any] | None = None,
) -> None:
    job.status = status
    job.progress = 100 if status == "completed" else job.progress
    job.public_message = _safe_message(message, "Work finished.")
    job.failure_code = _safe_code(failure_code) if failure_code else None
    job.result_json = (
        _encoded_json(result, limit=MAX_RESULT_BYTES) if result is not None else None
    )
    job.active_key = None
    job.lease_owner = None
    job.lease_expires_at = None
    job.heartbeat_at = now
    job.finished_at = now
    job.updated_at = now


class JobContext:
    def __init__(self, job_id: str, *, attempt: int = 1):
        self.job_id = job_id
        self.attempt = max(1, int(attempt))
        self._stop = threading.Event()
        self._cancelled = threading.Event()
        self._heartbeat_thread: threading.Thread | None = None
        self._last_poll = 0.0

    def start_heartbeat(self) -> None:
        def heartbeat() -> None:
            while not self._stop.wait(DEFAULT_LEASE_SECONDS / 3):
                if not self._heartbeat():
                    return

        self._heartbeat_thread = threading.Thread(
            target=heartbeat,
            name=f"godfin-job-heartbeat-{self.job_id[:8]}",
            daemon=True,
        )
        self._heartbeat_thread.start()

    def stop_heartbeat(self) -> None:
        self._stop.set()
        if self._heartbeat_thread is not None:
            self._heartbeat_thread.join(timeout=1)

    def retry_delay_seconds(self) -> float:
        """Return the deterministic queue backoff for this attempt."""
        return _retry_delay_seconds(self.job_id, self.attempt)

    def _heartbeat(self) -> bool:
        now = utcnow_naive()

        def update(db):
            job = db.query(BackgroundJob).filter_by(
                id=self.job_id,
                lease_owner=_worker_id,
            ).first()
            if job is None or job.status not in {"running", "cancel_requested"}:
                return False
            if job.cancel_requested or job.status == "cancel_requested":
                self._cancelled.set()
            job.heartbeat_at = now
            job.lease_expires_at = now + timedelta(seconds=DEFAULT_LEASE_SECONDS)
            job.updated_at = now
            return True

        return bool(_write_with_lock_retry(update))

    def check_cancelled(self) -> None:
        if _worker_stop.is_set():
            raise JobExecutionError("WORKER_STOPPING", retryable=True)
        now = time.monotonic()
        if now - self._last_poll >= CANCELLATION_POLL_SECONDS:
            self._heartbeat()
            self._last_poll = now
        if self._cancelled.is_set():
            raise JobCancelled("Background work was cancelled")

    def progress(
        self,
        progress: int,
        *,
        total: int | None = None,
        message: str | None = None,
    ) -> None:
        now = utcnow_naive()

        def update(db):
            job = db.query(BackgroundJob).filter_by(
                id=self.job_id,
                lease_owner=_worker_id,
            ).first()
            if job is None:
                raise JobExecutionError("JOB_LEASE_LOST", retryable=True)
            job.progress = max(0, min(99, int(progress)))
            if total is not None:
                job.total = max(0, int(total))
            if message is not None:
                job.public_message = _safe_message(message, "Work is in progress.")
            job.heartbeat_at = now
            job.lease_expires_at = now + timedelta(seconds=DEFAULT_LEASE_SECONDS)
            job.updated_at = now
            if job.cancel_requested:
                self._cancelled.set()

        _write_with_lock_retry(update)
        if self._cancelled.is_set():
            raise JobCancelled("Background work was cancelled")


def _complete_job(job_id: str, result: dict[str, Any] | None) -> None:
    now = utcnow_naive()

    def update(db):
        job = db.query(BackgroundJob).filter_by(
            id=job_id,
            lease_owner=_worker_id,
        ).first()
        if job is None:
            return
        if job.cancel_requested:
            _finish(job, "cancelled", now, "Work was cancelled.", None)
        else:
            _finish(job, "completed", now, "Work completed.", None, result=result)

    _write_with_lock_retry(update)


def _fail_job(
    job_id: str,
    *,
    code: str,
    retryable: bool,
    cancelled: bool = False,
) -> None:
    now = utcnow_naive()

    def update(db):
        job = db.query(BackgroundJob).filter_by(
            id=job_id,
            lease_owner=_worker_id,
        ).first()
        if job is None:
            return
        job.lease_owner = None
        job.lease_expires_at = None
        job.heartbeat_at = now
        job.updated_at = now
        if cancelled or job.cancel_requested:
            _finish(job, "cancelled", now, "Work was cancelled.", None)
        elif retryable and job.attempt < job.max_attempts:
            job.status = "retry_wait"
            job.failure_code = _safe_code(code)
            job.public_message = "Work will retry safely."
            job.available_at = now + timedelta(
                seconds=_retry_delay_seconds(job.id, job.attempt)
            )
        else:
            terminal = "poisoned" if job.attempt >= job.max_attempts else "failed"
            _finish(
                job,
                terminal,
                now,
                "Work could not be completed.",
                code,
            )

    _write_with_lock_retry(update)


def _claimed_job_details(job_id: str) -> tuple[str, dict[str, Any], int] | None:
    """Load a claimed job without abandoning its lease on a short SQLite lock."""

    def load(db):
        job = db.query(BackgroundJob).filter_by(id=job_id).one_or_none()
        if job is None:
            return None
        return job.kind, _decoded_json(job.payload_json), job.attempt

    return _write_with_lock_retry(load)


def _execute_job(job_id: str) -> None:
    context: JobContext | None = None
    try:
        try:
            details = _claimed_job_details(job_id)
        except JobExecutionError as exc:
            _fail_job(job_id, code=exc.code, retryable=exc.retryable)
            return
        if details is None:
            return
        kind, payload, attempt = details
        context = JobContext(job_id, attempt=attempt)
        with _handlers_lock:
            handler = _handlers.get(kind)
        if handler is None:
            _fail_job(job_id, code="JOB_HANDLER_UNAVAILABLE", retryable=False)
            return
        context.start_heartbeat()
        try:
            context.check_cancelled()
            result = handler(context, payload)
            context.check_cancelled()
            _complete_job(job_id, result)
        except JobCancelled:
            _fail_job(job_id, code="JOB_CANCELLED", retryable=False, cancelled=True)
        except JobExecutionError as exc:
            _fail_job(job_id, code=exc.code, retryable=exc.retryable)
        except Exception as exc:
            logger.exception(
                "Background job failed",
                extra={
                    "operation_id": kind,
                    "error_code": "JOB_HANDLER_FAILED",
                    "cause_type": type(exc).__name__,
                },
            )
            _fail_job(job_id, code="JOB_HANDLER_FAILED", retryable=True)
    finally:
        if context is not None:
            context.stop_heartbeat()
        with _worker_lock:
            _active_threads.pop(job_id, None)
        _worker_wake.set()


def _dispatcher_loop() -> None:
    next_recovery = time.monotonic() + DEFAULT_LEASE_SECONDS
    while not _worker_stop.is_set():
        with _worker_lock:
            active_count = sum(thread.is_alive() for thread in _active_threads.values())
        while active_count < MAX_CONCURRENT_JOBS and not _worker_stop.is_set():
            job_id = _claim_next_job()
            if job_id is None:
                break
            thread = threading.Thread(
                target=_execute_job,
                args=(job_id,),
                name=f"godfin-background-job-{job_id[:8]}",
                daemon=True,
            )
            with _worker_lock:
                _active_threads[job_id] = thread
            thread.start()
            active_count += 1
        if time.monotonic() >= next_recovery:
            recover_expired_jobs()
            next_recovery = time.monotonic() + DEFAULT_LEASE_SECONDS
        _worker_wake.wait(DISPATCH_INTERVAL_SECONDS)
        _worker_wake.clear()


def start_background_job_worker() -> bool:
    global _dispatcher, _worker_id
    # Surface schema or database failures before the worker is reported as
    # started. A dispatcher that dies on its first lease-recovery query must not
    # make the application appear ready for durable work.
    recover_expired_jobs()
    with _worker_lock:
        if _dispatcher is not None and _dispatcher.is_alive():
            return False
        _worker_id = uuid.uuid4().hex
        _worker_stop.clear()
        _worker_wake.clear()
        _dispatcher = threading.Thread(
            target=_dispatcher_loop,
            name="godfin-background-dispatcher",
            daemon=True,
        )
        _dispatcher.start()
        return True


def stop_background_job_worker(timeout: float = 5.0) -> None:
    global _dispatcher
    _worker_stop.set()
    _worker_wake.set()
    dispatcher = _dispatcher
    if dispatcher is not None:
        dispatcher.join(timeout=max(0.0, timeout))
    with _worker_lock:
        active = list(_active_threads.values())
    deadline = time.monotonic() + max(0.0, timeout)
    for thread in active:
        thread.join(timeout=max(0.0, deadline - time.monotonic()))
    with _worker_lock:
        if _dispatcher is dispatcher:
            _dispatcher = None


def request_job_cancel(job_id: str) -> bool:
    now = utcnow_naive()

    def update(db):
        job = db.query(BackgroundJob).filter_by(id=job_id).first()
        if job is None or job.status in TERMINAL_STATUSES:
            return False
        job.cancel_requested = True
        job.updated_at = now
        if job.status in {"queued", "retry_wait"}:
            _finish(job, "cancelled", now, "Work was cancelled.", None)
        else:
            job.status = "cancel_requested"
            job.public_message = "Stopping work safely…"
        return True

    requested = bool(_write_with_lock_retry(update))
    if requested:
        _worker_wake.set()
    return requested


def latest_job(*, kind: str | None = None, active_key: str | None = None) -> dict[str, Any] | None:
    db = _session()
    try:
        query = db.query(BackgroundJob)
        if active_key is not None:
            if kind is not None:
                query = query.filter(
                    BackgroundJob.kind == kind,
                    (BackgroundJob.active_key == active_key)
                    | (BackgroundJob.active_key.is_(None)),
                )
            else:
                query = query.filter(BackgroundJob.active_key == active_key)
        elif kind is not None:
            query = query.filter(BackgroundJob.kind == kind)
        else:
            raise ValueError("A kind or active key is required")
        job = query.order_by(BackgroundJob.created_at.desc()).first()
        return public_job(job) if job is not None else None
    finally:
        db.close()


def public_job(job: BackgroundJob) -> dict[str, Any]:
    return {
        "id": job.id,
        "kind": job.kind,
        "status": job.status,
        "progress": job.progress,
        "total": job.total,
        "message": job.public_message,
        "failure_code": job.failure_code,
        "attempt": job.attempt,
        "max_attempts": job.max_attempts,
        "retry_at": job.available_at.isoformat() if job.status == "retry_wait" else None,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "result": _decoded_json(job.result_json) if job.result_json else None,
        "cancel_requested": bool(job.cancel_requested),
    }


def job_queue_summary(db: Any | None = None) -> dict[str, Any]:
    owns_session = db is None
    if owns_session:
        db = _session()
    try:
        counts = {
            status: 0
            for status in (*sorted(ACTIVE_STATUSES), *sorted(TERMINAL_STATUSES))
        }
        counts.update(
            {
                status: int(count)
                for status, count in db.query(
                    BackgroundJob.status,
                    func.count(BackgroundJob.id),
                )
                .group_by(BackgroundJob.status)
                .all()
            }
        )
        oldest = (
            db.query(BackgroundJob)
            .filter(BackgroundJob.status.in_(ACTIVE_STATUSES))
            .order_by(BackgroundJob.created_at)
            .first()
        )
        return {
            "counts": counts,
            "active": sum(counts[status] for status in ACTIVE_STATUSES),
            "capacity": MAX_PENDING_JOBS,
            "worker_running": bool(_dispatcher and _dispatcher.is_alive()),
            "registered_kinds": list(registered_job_kinds()),
            "oldest_active_at": oldest.created_at.isoformat() if oldest else None,
        }
    finally:
        if owns_session:
            db.close()
