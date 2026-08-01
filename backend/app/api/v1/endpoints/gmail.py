from __future__ import annotations

import logging
import json
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.auth import get_current_user, hash_token
from app.core.backup import create_backup
from app.core.config import settings as app_config
from app.core.database import get_db
from app.core.gmail_service import (
    GmailConfigurationError,
    GmailError,
    GmailOAuthStateError,
    OAUTH_REDIRECT_URI,
    gmail_service,
    is_connected,
    client_config_available,
)
from app.core.ingestion import (
    get_ingestion_history, run_ingestion, run_ingestion_with_dates,
    run_ingestion_with_dates_background,
    run_initial_sync, run_initial_sync_background,
)
from app.core.scheduler import _set_manual_ingestion_running
from app.core.pin_security import client_ip_from_request, require_current_pin
from app.models.app_setting import AppSetting

logger = logging.getLogger(__name__)
router = APIRouter()


# --- Gmail OAuth ---

@router.get("/auth/gmail/url")
def get_gmail_auth_url(
    request: Request,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Create a short-lived installed-app OAuth attempt for this session."""
    try:
        if not client_config_available():
            raise HTTPException(
                status_code=503,
                detail=(
                    "Gmail connection is not configured for this GODFIN build yet. "
                    "The app owner must add the dedicated desktop Google connection."
                ),
            )

        authorization = request.headers.get("authorization", "")
        session_token = authorization[7:] if authorization.startswith("Bearer ") else ""
        auth_url = gmail_service.get_auth_url(
            db,
            session_token_hash=hash_token(session_token),
            redirect_uri=OAUTH_REDIRECT_URI,
        )
        return {
            "auth_url": auth_url,
            "flow": "loopback",
            "expires_in_seconds": 600,
        }

    except HTTPException:
        raise
    except GmailConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to start Gmail authorization")
        raise HTTPException(
            status_code=500,
            detail="Gmail connection could not be started. Try again.",
        ) from exc


@router.get("/auth/gmail/callback")
def gmail_oauth_callback(
    code: str = Query(None),
    state: str = Query(None),
    error: str = Query(None),
    db: Session = Depends(get_db),
):
    """Validate one-time state and complete the fixed loopback callback."""

    if error:
        try:
            gmail_service.cancel_auth(
                db,
                state=state or "",
                redirect_uri=OAUTH_REDIRECT_URI,
            )
        except GmailOAuthStateError:
            pass
        return HTMLResponse(
            content=(
                "<!doctype html><title>GODFIN Gmail connection</title>"
                "<main style='font:16px system-ui;padding:48px;max-width:620px'>"
                "<h1>Gmail was not connected</h1>"
                "<p>Return to GODFIN and try again when you are ready. "
                "No email was imported.</p></main>"
            ),
            status_code=400,
        )

    if not code:
        return HTMLResponse(
            content=(
                "<!doctype html><title>GODFIN Gmail connection</title>"
                "<main style='font:16px system-ui;padding:48px;max-width:620px'>"
                "<h1>Gmail could not be connected</h1>"
                "<p>The approval response was incomplete. Return to GODFIN and start again.</p>"
                "</main>"
            ),
            status_code=400,
        )

    try:
        success = gmail_service.complete_auth(
            db,
            authorization_code=code,
            state=state or "",
            redirect_uri=OAUTH_REDIRECT_URI,
        )

        if success:
            return HTMLResponse(
                content=(
                    "<!doctype html><title>GODFIN Gmail connected</title>"
                    "<main style='font:16px system-ui;padding:48px;max-width:620px'>"
                    "<h1>Gmail is connected</h1>"
                    "<p>You can close this tab and return to GODFIN. "
                    "The app will notice the connection automatically.</p>"
                    "<script>setTimeout(function(){window.close()},1500)</script></main>"
                )
            )
        return HTMLResponse(
            content=(
                "<!doctype html><title>GODFIN Gmail connection</title>"
                "<main style='font:16px system-ui;padding:48px;max-width:620px'>"
                "<h1>Gmail could not be connected</h1>"
                "<p>Return to GODFIN and try again. No email was imported.</p></main>"
            ),
            status_code=400,
        )
    except GmailError as exc:
        logger.warning("Gmail OAuth callback rejected: %s", exc.code)
        return HTMLResponse(
            content=(
                "<!doctype html><title>GODFIN Gmail connection</title>"
                "<main style='font:16px system-ui;padding:48px;max-width:620px'>"
                "<h1>Gmail could not be connected</h1>"
                "<p>Return to GODFIN and try again. No email was imported.</p></main>"
            ),
            status_code=400,
        )


@router.get("/auth/gmail/status")
def get_gmail_status(
    _user: bool = Depends(get_current_user),
):
    """Check if Gmail is connected."""
    if gmail_service.is_connected:
        email = gmail_service.get_user_email()
        return {
            "connected": True,
            "email": email,
            "digest_email_supported": gmail_service.can_send,
        }

    # Try to load credentials
    if gmail_service.load_credentials():
        email = gmail_service.get_user_email()
        return {
            "connected": True,
            "email": email,
            "digest_email_supported": gmail_service.can_send,
        }

    return {"connected": False, "digest_email_supported": False}


# --- Ingestion ---

@router.post("/ingest/gmail")
def trigger_ingestion(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Trigger manual Gmail ingestion."""
    from app.core.scheduler import _set_manual_ingestion_running

    if not gmail_service.is_connected:
        raise HTTPException(status_code=400, detail="Gmail not connected")

    try:
        # Set manual ingestion flag
        _set_manual_ingestion_running(db, True)

        result = run_ingestion(db)
        return result.to_dict()
    finally:
        # Clear manual ingestion flag
        _set_manual_ingestion_running(db, False)


@router.get("/ingest/status")
def ingestion_status(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    last_run = db.query(AppSetting).filter_by(key='last_ingestion_run').first()
    history_id = db.query(AppSetting).filter_by(key='last_gmail_history_id').first()

    return {
        "gmail_connected": gmail_service.is_connected,
        "last_run": last_run.value if last_run and last_run.value else None,
        "history_id": history_id.value if history_id and history_id.value else None,
        "history": get_ingestion_history(db),
    }


# --- Gmail Disconnect ---


class GmailDisconnectRequest(BaseModel):
    clear_data: bool = False
    pin: Optional[str] = Field(default=None, min_length=4, max_length=8)
    confirmation: Optional[str] = Field(default=None, max_length=50)


def _delete_gmail_transactions(db: Session) -> int:
    """Delete Gmail-derived rows only, in reviewed foreign-key order."""
    from app.core.goal_contributions import (
        recompute_goal_balance,
        void_goal_contribution,
    )
    from app.models.audit_log import AuditLog
    from app.models.classification_learning import ClassificationCorrection
    from app.models.goal import Goal
    from app.models.goal_contribution import (
        GoalContribution,
        GoalContributionSuggestion,
    )
    from app.models.transaction import Transaction
    from app.models.transaction_split import TransactionSplit
    from app.models.transfer_match import TransferMatch

    transaction_ids = [
        row[0]
        for row in db.query(Transaction.id)
        .filter(Transaction.source == "gmail")
        .all()
    ]
    if not transaction_ids:
        return 0

    affected_goal_ids: set[str] = set()
    contributions = (
        db.query(GoalContribution)
        .filter(GoalContribution.source_transaction_id.in_(transaction_ids))
        .all()
    )
    for contribution in contributions:
        affected_goal_ids.add(contribution.goal_id)
        if not contribution.is_voided:
            void_goal_contribution(
                db,
                contribution,
                reason="Gmail source data was deleted by the user.",
            )
        contribution.source_transaction_id = None

    db.query(GoalContributionSuggestion).filter(
        GoalContributionSuggestion.transaction_id.in_(transaction_ids)
    ).delete(synchronize_session=False)
    db.query(TransferMatch).filter(
        or_(
            TransferMatch.debit_transaction_id.in_(transaction_ids),
            TransferMatch.credit_transaction_id.in_(transaction_ids),
        )
    ).delete(synchronize_session=False)
    db.query(ClassificationCorrection).filter(
        ClassificationCorrection.transaction_id.in_(transaction_ids)
    ).delete(synchronize_session=False)
    db.query(TransactionSplit).filter(
        TransactionSplit.parent_transaction_id.in_(transaction_ids)
    ).delete(synchronize_session=False)
    db.query(AuditLog).filter(
        AuditLog.transaction_id.in_(transaction_ids)
    ).delete(synchronize_session=False)
    deleted = db.query(Transaction).filter(
        Transaction.id.in_(transaction_ids),
        Transaction.source == "gmail",
    ).delete(synchronize_session=False)

    for goal in db.query(Goal).filter(Goal.id.in_(affected_goal_ids)).all():
        recompute_goal_balance(db, goal)
    return int(deleted or 0)

@router.post("/auth/gmail/disconnect")
def gmail_disconnect(
    request: Request,
    body: GmailDisconnectRequest = Body(default=GmailDisconnectRequest()),
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Disconnect credentials and optionally delete only Gmail-derived data."""
    try:
        deleted_count = 0
        backup_filename = None
        if body.clear_data:
            require_current_pin(
                db,
                body.pin,
                client_ip_from_request(request),
            )
            if body.confirmation != "DELETE GMAIL DATA":
                raise HTTPException(
                    status_code=400,
                    detail="Type DELETE GMAIL DATA to confirm Gmail-data deletion.",
                )

            backup_setting = db.query(AppSetting).filter_by(
                key="backup_directory"
            ).first()
            backup_dir = backup_setting.value if backup_setting else "./backups"
            try:
                backup_filename = create_backup(
                    str(app_config.database_path),
                    backup_dir,
                )
            except Exception as exc:
                raise HTTPException(
                    status_code=503,
                    detail="Gmail data was not deleted because the safety backup failed.",
                ) from exc
            deleted_count = _delete_gmail_transactions(db)

        # Clear ingestion settings
        for key in ['last_gmail_history_id', 'last_ingestion_run',
                    'initial_sync_date_range', 'initial_sync_completed',
                    'last_manual_ingestion_range', 'last_manual_ingestion_date',
                    'last_auto_ingest_date', 'auto_ingestion_enabled',
                    'auto_ingestion_frequency', 'sync_result', 'sync_status',
                    'sync_error', 'sync_progress_processed', 'sync_progress_total']:
            setting = db.query(AppSetting).filter_by(key=key).first()
            if setting:
                db.delete(setting)
        db.commit()

        # Revoke credentials
        success = gmail_service.disconnect()

        if success:
            message = "Gmail disconnected successfully"
            if body.clear_data:
                message += f". {deleted_count} transactions removed."
            return {
                "success": True,
                "message": message,
                "deleted_transactions": deleted_count,
                "backup_filename": backup_filename,
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to disconnect Gmail")
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        logger.exception("Gmail disconnect failed")
        raise HTTPException(
            status_code=500,
            detail="Gmail could not be disconnected. No data was changed.",
        ) from exc


# --- Initial Sync ---

@router.post("/ingest/gmail/initial")
def trigger_initial_sync(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """
    Trigger initial sync from start of year to today.
    """
    if not is_connected():
        raise HTTPException(status_code=400, detail="Gmail not connected")

    # Check if initial sync already completed
    completed = db.query(AppSetting).filter_by(key='initial_sync_completed').first()
    if completed and completed.value == 'true':
        return {
            "success": True,
            "message": "Initial sync already completed. Use 'Ingest Now' for additional syncs.",
            "already_completed": True
        }

    try:
        result = run_initial_sync(db)
        return {
            "success": True,
            "result": result.to_dict(),
            "message": f"Initial sync complete. Created {result.created} transactions.",
        }
    except Exception as e:
        logger.error(f"Initial sync failed: {e}")
        raise HTTPException(status_code=500, detail=f"Initial sync failed: {str(e)}")


@router.post("/ingest/gmail/initial/start")
def start_initial_sync_background(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """
    Kick off initial sync as a background task. Returns immediately.
    Poll /ingest/gmail/sync-status for progress.
    """
    if not is_connected():
        raise HTTPException(status_code=400, detail="Gmail not connected")

    # Check if already running
    status_setting = db.query(AppSetting).filter_by(key='sync_status').first()
    if status_setting and status_setting.value == 'running':
        return {"success": True, "message": "Sync already in progress", "already_running": True}

    # Check if initial sync already completed
    completed = db.query(AppSetting).filter_by(key='initial_sync_completed').first()
    if completed and completed.value == 'true':
        return {
            "success": True,
            "message": "Initial sync already completed. Use 'Ingest Now' for additional syncs.",
            "already_completed": True,
        }

    background_tasks.add_task(run_initial_sync_background)

    return {"success": True, "message": "Initial sync started in background"}


@router.get("/ingest/gmail/sync-status")
def get_sync_status(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Poll endpoint for background sync progress."""
    keys = ['sync_status', 'sync_progress_processed', 'sync_progress_total', 'sync_result', 'sync_error']
    values = {}
    for key in keys:
        setting = db.query(AppSetting).filter_by(key=key).first()
        values[key] = setting.value if setting else ''

    processed = int(values['sync_progress_processed'] or 0)
    total = int(values['sync_progress_total'] or 0)

    raw_status = (values['sync_status'] or '').strip()
    # Treat empty or unknown values as 'idle'
    status = raw_status if raw_status in ('running', 'completed', 'partial', 'error') else 'idle'

    result_val = (values['sync_result'] or '').strip()

    # Only report 'completed' if initial_sync_completed is actually set.
    # This prevents stale sync data from showing after disconnect+reconnect.
    if status == 'completed':
        isc = db.query(AppSetting).filter_by(key='initial_sync_completed').first()
        if not isc or isc.value != 'true':
            # Stale data — reset everything to idle
            status = 'idle'
            result_val = ''
            processed = 0
            total = 0

    parsed_result = None
    if result_val:
        try:
            parsed_result = json.loads(result_val)
        except json.JSONDecodeError:
            parsed_result = None

    return {
        "status": status,
        "processed": processed,
        "total": total,
        "percent": round((processed / total) * 100, 1) if total > 0 else 0,
        "result": parsed_result,
        "error": (values['sync_error'] or '').strip() or None,
    }


# --- Ingest with Date Range ---

class DateRangeRequest(BaseModel):
    start_date: str  # YYYY-MM-DD
    end_date: str    # YYYY-MM-DD


@router.post("/ingest/gmail/range")
def trigger_ingestion_range(
    request: DateRangeRequest,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """
    Trigger ingestion for a specific date range.
    """
    if not is_connected():
        raise HTTPException(status_code=400, detail="Gmail not connected")

    # Validate dates
    try:
        from datetime import date, datetime
        start = datetime.strptime(request.start_date, '%Y-%m-%d').date()
        end = datetime.strptime(request.end_date, '%Y-%m-%d').date()

        if start >= end:
            raise HTTPException(status_code=400, detail="Start date must be before end date")

        today = date.today()
        if end > today:
            raise HTTPException(status_code=400, detail="End date cannot be in the future")

    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    try:
        # Convert to Gmail query format (before_date is exclusive)
        from datetime import timedelta
        end_plus_one = (end + timedelta(days=1)).strftime('%Y-%m-%d')

        result = run_ingestion_with_dates(
            db,
            after_date=request.start_date,
            before_date=end_plus_one,
            is_manual=True
        )

        return {
            "success": True,
            "result": result.to_dict(),
            "date_range": f"{request.start_date} to {request.end_date}",
            "message": f"Ingestion complete. Processed {result.processed}, created {result.created}.",
        }
    except Exception as e:
        logger.error(f"Date range ingestion failed: {e}")
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")


# --- Background Date Range Ingestion ---

@router.post("/ingest/gmail/range/start")
def start_ingestion_range_background(
    request: DateRangeRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """
    Kick off date-range ingestion as a background task. Returns immediately.
    Poll /ingest/gmail/range/status for progress.
    """
    if not is_connected():
        raise HTTPException(status_code=400, detail="Gmail not connected")

    # Validate dates
    try:
        from datetime import date as date_cls, datetime as dt_cls, timedelta
        start = dt_cls.strptime(request.start_date, '%Y-%m-%d').date()
        end = dt_cls.strptime(request.end_date, '%Y-%m-%d').date()

        if start >= end:
            raise HTTPException(status_code=400, detail="Start date must be before end date")

        today = date_cls.today()
        if end > today:
            raise HTTPException(status_code=400, detail="End date cannot be in the future")

    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    # Check if already running
    status_setting = db.query(AppSetting).filter_by(key='ingest_now_status').first()
    if status_setting and status_setting.value == 'running':
        return {"success": True, "message": "Ingestion already in progress", "already_running": True}

    # end_date is inclusive in the UI, so add 1 day for the query
    from datetime import timedelta
    end_plus_one = (end + timedelta(days=1)).strftime('%Y-%m-%d')

    background_tasks.add_task(run_ingestion_with_dates_background, request.start_date, end_plus_one)

    return {"success": True, "message": "Ingestion started"}


@router.get("/ingest/gmail/range/status")
def get_ingestion_range_status(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Poll endpoint for background date-range ingestion progress."""
    keys = [
        'ingest_now_status', 'ingest_now_processed', 'ingest_now_total',
        'ingest_now_result', 'ingest_now_error',
        'ingest_now_batch_current', 'ingest_now_batch_total',
    ]
    values = {}
    for key in keys:
        setting = db.query(AppSetting).filter_by(key=key).first()
        values[key] = setting.value if setting else ''

    processed = int(values['ingest_now_processed'] or 0)
    total = int(values['ingest_now_total'] or 0)
    batch_current = int(values['ingest_now_batch_current'] or 0)
    batch_total = int(values['ingest_now_batch_total'] or 0)

    raw_status = (values['ingest_now_status'] or '').strip()
    status = raw_status if raw_status in ('running', 'completed', 'partial', 'error') else 'idle'

    result_val = (values['ingest_now_result'] or '').strip()

    # Parse result string back to dict if completed
    parsed_result = None
    if status in {'completed', 'partial'} and result_val:
        try:
            parsed_result = json.loads(result_val)
        except json.JSONDecodeError:
            # One-release compatibility for status written by older builds.
            try:
                import ast
                parsed_result = ast.literal_eval(result_val)
            except Exception:
                parsed_result = None

    return {
        "status": status,
        "processed": processed,
        "total": total,
        "batch_current": batch_current,
        "batch_total": batch_total,
        "percent": round((processed / total) * 100, 1) if total > 0 else 0,
        "result": parsed_result,
        "error": (values['ingest_now_error'] or '').strip() or None,
    }


# --- Scheduler/History Status ---

@router.get("/ingest/scheduler/status")
def scheduler_status(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """
    Get detailed ingestion history for display in UI.
    """
    return {
        "gmail_connected": gmail_service.is_connected,
        "history": get_ingestion_history(db),
    }


# --- Auto-Ingestion Settings ---

@router.get("/ingest/settings")
def get_ingest_settings(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Get auto-ingestion settings."""
    from app.core.scheduler import _is_auto_ingestion_enabled, _get_ingestion_frequency
    from datetime import date, datetime, timedelta
    from app.models.transaction import Transaction

    enabled = _is_auto_ingestion_enabled(db)
    frequency = _get_ingestion_frequency(db)

    # Get last auto ingestion details
    last_run_setting = db.query(AppSetting).filter_by(key='last_ingestion_run').first()
    last_run = None
    last_status = None
    last_count = 0
    last_error = None

    if last_run_setting and last_run_setting.value:
        try:
            last_run = datetime.fromisoformat(last_run_setting.value)
            # Convert to local timezone for display
            last_run = last_run.replace(tzinfo=None)
        except ValueError:
            pass

    status_setting = db.query(AppSetting).filter_by(key='last_auto_ingestion_status').first()
    if status_setting:
        last_status = status_setting.value

    count_setting = db.query(AppSetting).filter_by(key='last_auto_ingestion_count').first()
    if count_setting and count_setting.value:
        try:
            last_count = int(count_setting.value)
        except ValueError:
            pass

    error_setting = db.query(AppSetting).filter_by(key='last_auto_ingestion_error').first()
    if error_setting and error_setting.value:
        last_error = error_setting.value

    # Calculate next run time - from now, not from last run (so frequency changes take effect immediately)
    next_run = None
    if enabled:
        now = datetime.now()
        next_run = now + timedelta(minutes=frequency)

    # Get monthly transaction count (current month only, exclude deleted)
    now = datetime.now()
    month_start = date(now.year, now.month, 1)
    monthly_count = db.query(Transaction).filter(
        Transaction.date >= month_start,
        Transaction.status != 'deleted',
    ).count()

    return {
        "auto_ingestion_enabled": enabled,
        "frequency_minutes": frequency,
        "last_auto_ingestion": {
            "timestamp": last_run.isoformat() if last_run else None,
            "status": last_status,
            "new_transactions": last_count,
            "error": last_error,
        } if last_run else None,
        "next_auto_ingestion": next_run.isoformat() if next_run else None,
        "monthly_transaction_count": monthly_count,
    }


class IngestSettingsRequest(BaseModel):
    enabled: bool = True
    frequency_minutes: int = 15


@router.post("/ingest/settings")
def update_ingest_settings(
    request: IngestSettingsRequest,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Update auto-ingestion settings."""
    from app.core.scheduler import _get_ingestion_frequency, reschedule_polling_job

    enabled = request.enabled
    frequency_minutes = request.frequency_minutes

    # Validate frequency
    if frequency_minutes < 5:
        raise HTTPException(status_code=400, detail="Frequency must be at least 5 minutes")
    if frequency_minutes > 1440:
        raise HTTPException(status_code=400, detail="Frequency cannot exceed 24 hours (1440 minutes)")

    # Get old frequency before updating
    old_frequency = _get_ingestion_frequency(db)

    # Update settings
    auto_enabled = db.query(AppSetting).filter_by(key='auto_ingestion_enabled').first()
    if not auto_enabled:
        auto_enabled = AppSetting(key='auto_ingestion_enabled', value=str(enabled).lower())
        db.add(auto_enabled)
    else:
        auto_enabled.value = str(enabled).lower()

    freq_setting = db.query(AppSetting).filter_by(key='ingestion_frequency_minutes').first()
    if not freq_setting:
        freq_setting = AppSetting(key='ingestion_frequency_minutes', value=str(frequency_minutes))
        db.add(freq_setting)
    else:
        freq_setting.value = str(frequency_minutes)

    db.commit()

    # Reschedule polling job if frequency changed
    rescheduled = False
    if old_frequency != frequency_minutes:
        rescheduled = reschedule_polling_job(frequency_minutes)

    return {
        "success": True,
        "auto_ingestion_enabled": enabled,
        "frequency_minutes": frequency_minutes,
        "rescheduled": rescheduled,
        "message": "Settings updated successfully",
    }
