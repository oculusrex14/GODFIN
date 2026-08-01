from __future__ import annotations

import logging
import random
import threading
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Scheduler is optional — only initialize if apscheduler is available
_scheduler = None

# Track ingestion state to prevent concurrent runs within the desktop process.
_ingestion_lock = threading.Lock()
_last_ingestion_attempt: Optional[datetime] = None
_ingestion_retry_attempts = 0


def _retry_delay_seconds(attempt: int) -> float:
    """Bounded exponential delay with 0–20% jitter."""
    base = min(3600.0, 30.0 * (2 ** max(0, attempt - 1)))
    return base + random.uniform(0, base * 0.2)


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


def start_scheduler(db_path: str, backup_dir: str) -> None:
    """Start background scheduler with polling and nightly batch jobs."""
    scheduler = _get_scheduler()
    if scheduler is None:
        return

    from app.core.backup import create_backup

    def nightly_batch():
        logger.info("Running nightly batch job")
        try:
            create_backup(db_path, backup_dir)
            logger.info("Nightly backup complete")
        except Exception as e:
            logger.error(f"Nightly batch error: {e}")

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
    logger.info(f"Scheduler started with nightly batch and {initial_frequency}-min polling")


def stop_scheduler() -> None:
    """Gracefully stop the scheduler."""
    scheduler = _get_scheduler()
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
