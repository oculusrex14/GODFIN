"""Registration boundary for durable background operations."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from app.core.background_jobs import (
    JobContext,
    JobExecutionError,
    register_job_handler,
)


def _initial_gmail_sync(context: JobContext, _payload: dict) -> dict:
    from app.core.ingestion import run_initial_sync_background

    return run_initial_sync_background(job_context=context)


def _date_range_gmail_sync(context: JobContext, payload: dict) -> dict:
    from app.core.ingestion import run_ingestion_with_dates_background

    start_date = str(payload.get("start_date") or "")
    end_date = str(payload.get("end_date") or "")
    if not start_date or not end_date:
        raise JobExecutionError("GMAIL_RANGE_INVALID", retryable=False)
    return run_ingestion_with_dates_background(
        start_date,
        end_date,
        job_context=context,
    )


def _scheduled_gmail_sync(context: JobContext, _payload: dict) -> dict:
    from app.core import database as database_module
    from app.core.gmail_service import is_connected
    from app.core.ingestion import run_scheduled_ingestion_background
    from app.core.scheduler import (
        _is_auto_ingestion_enabled,
        _update_last_run,
    )

    db = database_module.SessionLocal()
    try:
        if not _is_auto_ingestion_enabled(db):
            return {"skipped": "disabled"}
        if not is_connected():
            return {"skipped": "gmail_not_connected"}
        # End the settings read transaction before any Gmail network request.
        db.rollback()
        result = run_scheduled_ingestion_background(job_context=context)
        context.progress(95, message="Finishing the automatic Gmail import…")
        _update_last_run(
            success=True,
            new_transactions=int(result.get("created", 0)),
        )
        return result
    except Exception as exc:
        db.rollback()
        failure_code = str(
            getattr(exc, "code", "AUTOMATIC_INGESTION_FAILED")
        )[:80]
        _update_last_run(success=False, error_code=failure_code)
        raise JobExecutionError(
            failure_code,
            retryable=bool(getattr(exc, "retryable", True)),
        ) from exc
    finally:
        db.close()


def _automatic_backup(context: JobContext, _payload: dict) -> dict:
    from app.core.backup import create_backup
    from app.core.config import settings
    from app.core.scheduler import (
        _record_backup_failure,
        _record_backup_success,
    )

    context.progress(10, message="Creating the automatic safety backup…")
    backup_dir = os.environ.get("GODFIN_BACKUP_DIR", "./backups")
    try:
        filename = create_backup(str(settings.database_path), backup_dir)
    except Exception as exc:
        retry_at = datetime.now(timezone.utc) + timedelta(
            seconds=context.retry_delay_seconds()
        )
        _record_backup_failure(
            "automatic_backup_failed",
            retry_at,
            context.attempt,
        )
        raise JobExecutionError("AUTOMATIC_BACKUP_FAILED", retryable=True) from exc
    _record_backup_success(filename)
    context.progress(99, message="Automatic safety backup created.")
    return {"backup_created": True}


def _weekly_digest(context: JobContext, _payload: dict) -> dict:
    from app.core import database as database_module
    from app.core.advisor_digest import build_weekly_digest, digest_to_html
    from app.core.gmail_service import gmail_service
    from app.core.license import license_status
    from app.models.app_setting import AppSetting

    db = database_module.SessionLocal()
    try:
        enabled = db.query(AppSetting).filter_by(
            key="advisor_weekly_digest_enabled"
        ).first()
        recipient = db.query(AppSetting).filter_by(
            key="advisor_weekly_digest_recipient"
        ).first()
        if not enabled or enabled.value != "true" or not recipient or not recipient.value:
            return {"skipped": "disabled"}
        if "advanced_reports" not in license_status(db)["features"]:
            return {"skipped": "license_inactive"}
        context.progress(20, message="Preparing the weekly money summary…")
        digest = build_weekly_digest(db)
        db.rollback()
        context.check_cancelled()
        gmail_service.send_email(
            recipient.value,
            f"GODFIN weekly digest · {digest['period']['end']}",
            digest_to_html(digest),
        )
        setting = db.query(AppSetting).filter_by(
            key="advisor_weekly_digest_last_sent"
        ).first()
        if setting is None:
            setting = AppSetting(key="advisor_weekly_digest_last_sent", value="")
            db.add(setting)
        setting.value = datetime.now(timezone.utc).isoformat()
        db.commit()
        context.progress(99, message="Weekly money summary sent.")
        return {"sent": True}
    except JobExecutionError:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise JobExecutionError("WEEKLY_DIGEST_FAILED", retryable=True) from exc
    finally:
        db.close()


def register_default_job_handlers() -> None:
    from app.core.embedding_service import run_embedding_setup_job

    register_job_handler("gmail_initial_sync", _initial_gmail_sync)
    register_job_handler("gmail_date_range", _date_range_gmail_sync)
    register_job_handler("gmail_scheduled", _scheduled_gmail_sync)
    register_job_handler("automatic_backup", _automatic_backup)
    register_job_handler("weekly_digest", _weekly_digest)
    register_job_handler("embedding_setup", run_embedding_setup_job)
