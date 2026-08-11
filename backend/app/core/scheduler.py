from __future__ import annotations

import logging
import random
import threading
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Scheduler is optional — only initialize if apscheduler is available
_scheduler = None
_scheduler_lock = threading.RLock()
_scheduler_retry_timer: Optional[threading.Timer] = None
_backup_retry_timer: Optional[threading.Timer] = None
_scheduler_retry_attempts = 0
_backup_retry_attempts = 0
_shutdown_requested = False

# Track ingestion state to prevent concurrent runs within the desktop process.
_ingestion_lock = threading.Lock()
_last_ingestion_attempt: Optional[datetime] = None
_ingestion_retry_attempts = 0


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat()


def _save_health_values(values: dict[str, str]) -> None:
    """Persist support-safe scheduler state without exposing raw exceptions."""
    from app.core.database import SessionLocal
    from app.models.app_setting import AppSetting

    db = SessionLocal()
    try:
        existing = {
            setting.key: setting
            for setting in db.query(AppSetting)
            .filter(AppSetting.key.in_(tuple(values)))
            .all()
        }
        for key, value in values.items():
            setting = existing.get(key)
            if setting is None:
                setting = AppSetting(key=key, value=value)
                db.add(setting)
            else:
                setting.value = value
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning(
            "Could not persist backup protection health (%s)",
            type(exc).__name__,
        )
    finally:
        db.close()


def _record_scheduler_operational() -> None:
    _save_health_values(
        {
            "backup_scheduler_status": "operational",
            "backup_scheduler_failure_code": "",
            "backup_scheduler_next_retry_at": "",
            "backup_scheduler_failure_count": "0",
        }
    )


def _record_scheduler_failure(code: str, retry_at: datetime, attempt: int) -> None:
    _save_health_values(
        {
            "backup_scheduler_status": "degraded",
            "backup_scheduler_failure_code": code,
            "backup_scheduler_last_failure_at": _iso(_utc_now()),
            "backup_scheduler_next_retry_at": _iso(retry_at),
            "backup_scheduler_failure_count": str(attempt),
        }
    )


def _record_backup_success(filename: str) -> None:
    _save_health_values(
        {
            "backup_job_status": "ok",
            "backup_last_success_at": _iso(_utc_now()),
            "backup_last_filename": filename,
            "backup_job_failure_code": "",
            "backup_job_next_retry_at": "",
            "backup_job_failure_count": "0",
        }
    )


def _record_backup_failure(code: str, retry_at: datetime, attempt: int) -> None:
    _save_health_values(
        {
            "backup_job_status": "degraded",
            "backup_job_failure_code": code,
            "backup_job_last_failure_at": _iso(_utc_now()),
            "backup_job_next_retry_at": _iso(retry_at),
            "backup_job_failure_count": str(attempt),
        }
    )


def _record_backup_retry_pending(retry_at: datetime, attempt: int) -> None:
    """Update retry timing without rewriting the original failure evidence."""
    _save_health_values(
        {
            "backup_job_status": "degraded",
            "backup_job_next_retry_at": _iso(retry_at),
            "backup_job_failure_count": str(attempt),
        }
    )


def _backup_retry_required() -> bool:
    from app.core.database import SessionLocal
    from app.models.app_setting import AppSetting

    db = SessionLocal()
    try:
        setting = (
            db.query(AppSetting)
            .filter_by(key="backup_job_status")
            .first()
        )
        return bool(setting and setting.value == "degraded")
    except Exception as exc:
        logger.warning(
            "Could not read persisted backup protection health (%s)",
            type(exc).__name__,
        )
        return False
    finally:
        db.close()


def _retry_delay_seconds(attempt: int) -> float:
    """Bounded exponential delay with 0–20% jitter."""
    base = min(3600.0, 30.0 * (2 ** max(0, attempt - 1)))
    return base + random.uniform(0, base * 0.2)


def _cancel_timer(timer: Optional[threading.Timer]) -> None:
    if timer is not None:
        timer.cancel()


def _schedule_scheduler_retry(db_path: str, backup_dir: str, code: str) -> None:
    global _scheduler_retry_attempts, _scheduler_retry_timer

    with _scheduler_lock:
        if _shutdown_requested:
            return
        if _scheduler_retry_timer is not None and _scheduler_retry_timer.is_alive():
            return
        _scheduler_retry_attempts += 1
        delay = _retry_delay_seconds(_scheduler_retry_attempts)
        retry_at = _utc_now() + timedelta(seconds=delay)
        _record_scheduler_failure(code, retry_at, _scheduler_retry_attempts)

        def retry() -> None:
            global _scheduler_retry_timer
            with _scheduler_lock:
                _scheduler_retry_timer = None
                if _shutdown_requested:
                    return
            try:
                start_scheduler(db_path, backup_dir)
            except Exception as exc:
                logger.error(
                    "Backup scheduler retry failed (%s)",
                    type(exc).__name__,
                )
                _schedule_scheduler_retry(db_path, backup_dir, code)

        timer = threading.Timer(delay, retry)
        timer.daemon = True
        _scheduler_retry_timer = timer
        timer.start()
        logger.warning(
            "Backup scheduler is degraded; retry %d is scheduled in %.1f seconds",
            _scheduler_retry_attempts,
            delay,
        )


def _schedule_backup_retry(job: Callable[[], None]) -> tuple[int, datetime]:
    global _backup_retry_attempts, _backup_retry_timer

    with _scheduler_lock:
        _backup_retry_attempts += 1
        delay = _retry_delay_seconds(_backup_retry_attempts)
        retry_at = _utc_now() + timedelta(seconds=delay)
        _cancel_timer(_backup_retry_timer)

        def retry() -> None:
            global _backup_retry_timer
            with _scheduler_lock:
                _backup_retry_timer = None
                if _shutdown_requested:
                    return
            job()

        timer = threading.Timer(delay, retry)
        timer.daemon = True
        _backup_retry_timer = timer
        if not _shutdown_requested:
            timer.start()
        return _backup_retry_attempts, retry_at


def _get_scheduler():
    global _scheduler
    if _scheduler is None:
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            _scheduler = BackgroundScheduler()
        except ImportError:
            logger.warning("APScheduler not installed — background jobs disabled")
            return None
    return _scheduler


def _is_auto_ingestion_enabled(db: Session) -> bool:
    """Check if auto-ingestion is enabled in settings."""
    from app.models.app_setting import AppSetting
    setting = db.query(AppSetting).filter_by(key='auto_ingestion_enabled').first()
    return setting.value == 'true' if setting else True  # Default to enabled


def _get_ingestion_frequency(db: Session) -> int:
    """Get ingestion frequency in minutes."""
    from app.models.app_setting import AppSetting
    setting = db.query(AppSetting).filter_by(key='ingestion_frequency_minutes').first()
    if setting and setting.value:
        try:
            return int(setting.value)
        except ValueError:
            pass
    return 15  # Default 15 minutes


def _is_manual_ingestion_running(db: Session) -> bool:
    """Check if a manual ingestion is currently running."""
    from app.models.app_setting import AppSetting
    setting = db.query(AppSetting).filter_by(key='manual_ingestion_running').first()
    if setting and setting.value:
        try:
            start_time = datetime.fromisoformat(setting.value)
            # Consider it running if started within last 30 minutes
            if datetime.now(timezone.utc) - start_time < timedelta(minutes=30):
                return True
            else:
                # Clear stale flag
                setting.value = ''
                db.commit()
        except ValueError:
            pass
    return False


def _set_manual_ingestion_running(db: Session, running: bool):
    """Set or clear the manual ingestion running flag."""
    from app.models.app_setting import AppSetting
    setting = db.query(AppSetting).filter_by(key='manual_ingestion_running').first()
    if not setting:
        setting = AppSetting(key='manual_ingestion_running', value='')
        db.add(setting)
    setting.value = datetime.now(timezone.utc).isoformat() if running else ''
    db.commit()


def start_scheduler(db_path: str, backup_dir: str) -> bool:
    """Start background scheduler with polling and nightly batch jobs."""
    global _backup_retry_attempts, _scheduler_retry_attempts
    global _scheduler_retry_timer, _shutdown_requested

    _shutdown_requested = False
    scheduler = _get_scheduler()
    if scheduler is None:
        _schedule_scheduler_retry(
            db_path,
            backup_dir,
            "scheduler_dependency_unavailable",
        )
        return False
    if scheduler.running:
        _record_scheduler_operational()
        return True

    from app.core.backup import create_backup

    def nightly_batch():
        global _backup_retry_attempts, _backup_retry_timer

        logger.info("Running nightly batch job")
        try:
            filename = create_backup(db_path, backup_dir)
            with _scheduler_lock:
                _backup_retry_attempts = 0
                _cancel_timer(_backup_retry_timer)
                _backup_retry_timer = None
            _record_backup_success(filename)
            logger.info("Nightly backup complete")
        except Exception as exc:
            attempt, retry_at = _schedule_backup_retry(nightly_batch)
            _record_backup_failure("automatic_backup_failed", retry_at, attempt)
            logger.error(
                "Nightly backup failed (%s); bounded retry %d is scheduled",
                type(exc).__name__,
                attempt,
            )

    def polling_job():
        """Scheduled job to check for new Gmail transactions."""
        global _last_ingestion_attempt, _ingestion_retry_attempts

        # Prevent concurrent execution
        if not _ingestion_lock.acquire(blocking=False):
            logger.info("Skipping scheduled ingestion - another instance is running")
            return

        try:
            _last_ingestion_attempt = datetime.now(timezone.utc)

            from app.core.database import SessionLocal
            from app.core.gmail_service import is_connected
            from app.core.ingestion import run_ingestion

            db = SessionLocal()
            try:
                # Check if auto-ingestion is enabled
                if not _is_auto_ingestion_enabled(db):
                    logger.debug("Auto-ingestion is disabled")
                    return

                # Check if Gmail is connected
                if not is_connected():
                    logger.debug("Gmail not connected - skipping ingestion")
                    return

                # Check if manual ingestion is running
                if _is_manual_ingestion_running(db):
                    logger.info("Manual ingestion in progress - skipping scheduled run")
                    return

                logger.info("Starting scheduled ingestion")
                result = run_ingestion(db)

                if result.created > 0:
                    logger.info(f"Scheduled ingestion complete: {result.created} new transactions")
                else:
                    logger.debug(f"Scheduled ingestion complete: no new transactions")

                _update_last_run(success=True, new_transactions=result.created)
                _ingestion_retry_attempts = 0

            finally:
                db.close()

        except Exception as e:
            logger.error(f"Scheduled ingestion failed: {e}")
            _update_last_run(success=False, error_message=str(e)[:500])
            if bool(getattr(e, "retryable", False)):
                _ingestion_retry_attempts += 1
                delay = _retry_delay_seconds(_ingestion_retry_attempts)
                scheduler.add_job(
                    polling_job,
                    "date",
                    run_date=datetime.now(timezone.utc) + timedelta(seconds=delay),
                    id="polling_retry",
                    replace_existing=True,
                    max_instances=1,
                    misfire_grace_time=60,
                )
                logger.warning(
                    "Scheduled Gmail ingestion will retry in %.1f seconds",
                    delay,
                )
        finally:
            _ingestion_lock.release()

    def weekly_digest_job():
        """Generate and send an explicitly enabled digest from this device."""
        from app.core.advisor_digest import build_weekly_digest, digest_to_html
        from app.core.database import SessionLocal
        from app.core.gmail_service import gmail_service
        from app.core.license import license_status
        from app.models.app_setting import AppSetting

        db = SessionLocal()
        try:
            enabled = (
                db.query(AppSetting)
                .filter_by(key="advisor_weekly_digest_enabled")
                .first()
            )
            recipient = (
                db.query(AppSetting)
                .filter_by(key="advisor_weekly_digest_recipient")
                .first()
            )
            if not enabled or enabled.value != "true" or not recipient or not recipient.value:
                return
            if "advanced_reports" not in license_status(db)["features"]:
                logger.info("Skipping weekly digest because the paid license is inactive")
                return
            digest = build_weekly_digest(db)
            gmail_service.send_email(
                recipient.value,
                f"GODFIN weekly digest · {digest['period']['end']}",
                digest_to_html(digest),
            )
            setting = (
                db.query(AppSetting)
                .filter_by(key="advisor_weekly_digest_last_sent")
                .first()
            )
            if setting is None:
                setting = AppSetting(
                    key="advisor_weekly_digest_last_sent", value=""
                )
                db.add(setting)
            setting.value = datetime.now(timezone.utc).isoformat()
            db.commit()
            logger.info("Weekly advisor digest sent through the user's Gmail account")
        except Exception as error:
            logger.error("Weekly advisor digest failed: %s", error)
            db.rollback()
        finally:
            db.close()

    # Nightly batch at 23:59
    scheduler.add_job(
        nightly_batch,
        'cron',
        hour=23, minute=59,
        id='nightly_batch',
        replace_existing=True,
    )

    # Monday 08:00 local time. The digest job exits immediately unless the
    # user explicitly enabled delivery and connected Gmail with send access.
    scheduler.add_job(
        weekly_digest_job,
        "cron",
        day_of_week="mon",
        hour=8,
        minute=0,
        id="weekly_advisor_digest",
        replace_existing=True,
    )

    # Read frequency from database for initial scheduling
    initial_frequency = 15
    try:
        from app.core.database import SessionLocal
        from app.models.app_setting import AppSetting
        db = SessionLocal()
        freq_setting = db.query(AppSetting).filter_by(key='ingestion_frequency_minutes').first()
        if freq_setting and freq_setting.value:
            try:
                initial_frequency = int(freq_setting.value)
            except ValueError:
                pass
        db.close()
    except Exception:
        pass

    # Polling job - interval read from database, but job checks actual frequency internally
    scheduler.add_job(
        polling_job,
        'interval',
        minutes=initial_frequency,
        id='polling',
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60,
    )

    scheduler.start()
    with _scheduler_lock:
        _scheduler_retry_attempts = 0
        _cancel_timer(_scheduler_retry_timer)
        _scheduler_retry_timer = None
    _record_scheduler_operational()
    if _backup_retry_required():
        attempt, retry_at = _schedule_backup_retry(nightly_batch)
        _record_backup_retry_pending(retry_at, attempt)
    logger.info(f"Scheduler started with nightly batch and {initial_frequency}-min polling")
    return True


def schedule_scheduler_recovery(
    db_path: str,
    backup_dir: str,
    code: str = "scheduler_start_failed",
) -> None:
    """Persist a startup failure and retry without blocking API availability."""
    _schedule_scheduler_retry(db_path, backup_dir, code)


def stop_scheduler() -> None:
    """Gracefully stop the scheduler."""
    global _backup_retry_timer, _scheduler_retry_timer, _shutdown_requested

    _shutdown_requested = True
    with _scheduler_lock:
        _cancel_timer(_scheduler_retry_timer)
        _cancel_timer(_backup_retry_timer)
        _scheduler_retry_timer = None
        _backup_retry_timer = None
    scheduler = _scheduler
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")


def reschedule_polling_job(new_minutes: int) -> bool:
    """
    Reschedule the polling job with a new interval.
    Call this when user updates frequency settings.

    Args:
        new_minutes: New interval in minutes

    Returns:
        True if rescheduled, False if scheduler not running
    """
    scheduler = _get_scheduler()
    if not scheduler or not scheduler.running:
        logger.warning("Cannot reschedule - scheduler not running")
        return False

    try:
        # Remove existing job
        job = scheduler.get_job('polling')
        if job:
            scheduler.remove_job('polling')

        # Reschedule with new interval
        scheduler.add_job(
            polling_job,
            'interval',
            minutes=new_minutes,
            id='polling',
            replace_existing=True,
        )
        logger.info(f"Rescheduled polling job to run every {new_minutes} minutes")
        return True
    except Exception as e:
        logger.error(f"Failed to reschedule polling job: {e}")
        return False


def run_on_wake(db_path: str, backup_dir: str) -> None:
    """Check if we missed scheduled tasks and run them if needed."""
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from app.models.app_setting import AppSetting

        engine = create_engine(f'sqlite:///{db_path}')
        Session = sessionmaker(bind=engine)
        session = Session()

        setting = session.query(AppSetting).filter_by(key='last_ingestion_run').first()
        if setting and setting.value:
            last_run = datetime.fromisoformat(setting.value)
            minutes_since = (datetime.now(timezone.utc) - last_run).total_seconds() / 60
            if minutes_since > 20:  # More than polling interval + buffer
                logger.info(f"Missed {minutes_since:.0f} minutes — triggering catch-up")
                from app.core.backup import create_backup
                create_backup(db_path, backup_dir)

        session.close()
        engine.dispose()
    except Exception as e:
        logger.warning(f"Run-on-wake check failed: {e}")


def _update_last_run(success: bool = True, new_transactions: int = 0, error_message: str = ""):
    """Update the last_ingestion_run timestamp and status in settings."""
    try:
        from app.core.database import SessionLocal
        from app.models.app_setting import AppSetting

        db = SessionLocal()
        now = datetime.now(timezone.utc)

        # Update timestamp
        setting = db.query(AppSetting).filter_by(key='last_ingestion_run').first()
        if setting:
            setting.value = now.isoformat()
            db.commit()

        # Update status
        status_setting = db.query(AppSetting).filter_by(key='last_auto_ingestion_status').first()
        if not status_setting:
            status_setting = AppSetting(key='last_auto_ingestion_status', value='')
            db.add(status_setting)
        status_setting.value = 'success' if success else 'error'
        db.commit()

        # Update transaction count
        count_setting = db.query(AppSetting).filter_by(key='last_auto_ingestion_count').first()
        if not count_setting:
            count_setting = AppSetting(key='last_auto_ingestion_count', value='0')
            db.add(count_setting)
        count_setting.value = str(new_transactions)
        db.commit()

        # Update error message if failed
        if error_message:
            error_setting = db.query(AppSetting).filter_by(key='last_auto_ingestion_error').first()
            if not error_setting:
                error_setting = AppSetting(key='last_auto_ingestion_error', value='')
                db.add(error_setting)
            error_setting.value = error_message[:500]  # Limit to 500 chars
            db.commit()

        db.close()
    except Exception as e:
        logger.warning(f"Failed to update last_run: {e}")
