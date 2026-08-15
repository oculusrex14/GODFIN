from __future__ import annotations

import logging
import json
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.core.auth import get_current_user, hash_token
from app.core.background_jobs import (
    JobQueueFull,
    enqueue_job,
    latest_job,
    request_job_cancel,
)
from app.core.backup import create_backup
from app.core.config import settings as app_config
from app.core.data_deletion import delete_transactions_with_dependents
from app.core.database import get_db
from app.core.errors import IntegrationUnavailableError, StateConflictError
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
    run_initial_sync,
)
from app.core.pin_security import client_ip_from_request, require_current_pin
from app.models.app_setting import AppSetting

logger = logging.getLogger(__name__)
router = APIRouter()


class GmailAuthURLResponse(BaseModel):
    auth_url: str
    flow: str
    expires_in_seconds: int


class GmailStatusResponse(BaseModel):
    connected: bool
    email: str | None = None
    digest_email_supported: bool
    status: str
    message: str
    retryable: bool
    action_required: str | None


class IngestionResultResponse(BaseModel):
    processed: int
    created: int
    skipped_blacklist: int
    skipped_no_match: int
    skipped_duplicate: int
    skipped_finalized_period: int
    errors: int
    error_details: list[str]
    source_status: str
    retryable: bool
    full_resync: bool


class IngestionHistoryResponse(BaseModel):
    last_ingestion_run: str | None
    last_manual_ingestion_date: str | None
    last_manual_ingestion_range: str | None
    initial_sync_date_range: str | None
    initial_sync_completed: str | None


class IngestionStatusResponse(BaseModel):
    gmail_connected: bool
    last_run: str | None
    history_id: str | None
    history: IngestionHistoryResponse


class GmailDisconnectResponse(BaseModel):
    success: bool
    message: str
    deleted_transactions: int
    backup_filename: str | None


class InitialSyncResponse(BaseModel):
    success: bool
    result: IngestionResultResponse | None = None
    message: str
    already_completed: bool | None = None


class BackgroundIngestionStartResponse(BaseModel):
    success: bool
    message: str
    job_id: str | None = None
    started: bool | None = None
    already_running: bool | None = None
    already_completed: bool | None = None


class IngestionProgressResponse(BaseModel):
    status: str
    processed: int
    total: int
    percent: float
    result: IngestionResultResponse | None
    error: str | None
    job_id: str | None = None
    attempt: int | None = None
    retry_at: str | None = None


class RangeIngestionProgressResponse(IngestionProgressResponse):
    batch_current: int
    batch_total: int


class BackgroundCancelResponse(BaseModel):
    cancel_requested: bool
    job_id: str | None


class DateRangeIngestionResponse(BaseModel):
    success: bool
    result: IngestionResultResponse
    date_range: str
    message: str


class SchedulerStatusResponse(BaseModel):
    gmail_connected: bool
    history: IngestionHistoryResponse


class LastAutoIngestionResponse(BaseModel):
    timestamp: str
    status: str | None
    new_transactions: int
    error: str | None


class IngestSettingsResponse(BaseModel):
    auto_ingestion_enabled: bool
    frequency_minutes: int
    last_auto_ingestion: LastAutoIngestionResponse | None
    next_auto_ingestion: str | None
    monthly_transaction_count: int


class IngestSettingsUpdateResponse(BaseModel):
    success: bool
    auto_ingestion_enabled: bool
    frequency_minutes: int
    rescheduled: bool
    message: str


# --- Gmail OAuth ---

@router.get("/auth/gmail/url", response_model=GmailAuthURLResponse)
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
        raise IntegrationUnavailableError(
            code="GMAIL_CONFIGURATION_REQUIRED",
            message="Gmail connection is not configured for this GODFIN build yet.",
            hint="Add the dedicated desktop Google connection, then try again.",
            status_code=503,
            retriable=False,
        ) from exc
    except Exception as exc:
        logger.exception("Failed to start Gmail authorization")
        raise HTTPException(
            status_code=500,
            detail="Gmail connection could not be started. Try again.",
        ) from exc


@router.get(
    "/auth/gmail/callback",
    response_class=Response,
    responses={
        200: {
            "description": "Browser-safe Gmail connection result.",
            "content": {"text/html": {"schema": {"type": "string"}}},
        }
    },
)
def gmail_oauth_callback(
    code: str | None = Query(default=None, min_length=1, max_length=4096),
    state: str | None = Query(default=None, min_length=16, max_length=512),
    error: str | None = Query(default=None, min_length=1, max_length=200),
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


@router.get(
    "/auth/gmail/status",
    response_model=GmailStatusResponse,
    response_model_exclude_unset=True,
)
def get_gmail_status(
    _user: bool = Depends(get_current_user),
):
    """Check if Gmail is connected."""
    health = gmail_service.connection_health()
    if health.connected:
        email = gmail_service.get_user_email()
        return {
            "connected": True,
            "email": email,
            "digest_email_supported": gmail_service.can_send,
            **health.to_dict(),
        }
    return {
        "connected": False,
        "digest_email_supported": False,
        **health.to_dict(),
    }


# --- Ingestion ---

@router.post("/ingest/gmail", response_model=IngestionResultResponse)
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


@router.get("/ingest/status", response_model=IngestionStatusResponse)
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
    from app.models.transaction import Transaction

    transaction_ids = [
        row[0]
        for row in db.query(Transaction.id)
        .filter(Transaction.source == "gmail")
        .all()
    ]
    return delete_transactions_with_dependents(
        db,
        transaction_ids,
        void_reason="Gmail source data was deleted by the user.",
    )

@router.post("/auth/gmail/disconnect", response_model=GmailDisconnectResponse)
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
                action="delete_gmail_data",
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

@router.post(
    "/ingest/gmail/initial",
    response_model=InitialSyncResponse,
    response_model_exclude_unset=True,
)
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
    except Exception as exc:
        raise IntegrationUnavailableError(
            code="GMAIL_SYNC_FAILED",
            message="Gmail sync could not be completed.",
            hint="Check the Gmail connection and try again.",
        ) from exc


@router.post(
    "/ingest/gmail/initial/start",
    response_model=BackgroundIngestionStartResponse,
    response_model_exclude_unset=True,
)
def start_initial_sync_background(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """
    Kick off initial sync as a background task. Returns immediately.
    Poll /ingest/gmail/sync-status for progress.
    """
    if not is_connected():
        raise HTTPException(status_code=400, detail="Gmail not connected")

    # Check if initial sync already completed
    completed = db.query(AppSetting).filter_by(key='initial_sync_completed').first()
    if completed and completed.value == 'true':
        return {
            "success": True,
            "message": "Initial sync already completed. Use 'Ingest Now' for additional syncs.",
            "already_completed": True,
        }

    try:
        queued = enqueue_job(
            "gmail_initial_sync",
            active_key="gmail-ingestion",
            max_attempts=3,
            public_message="Preparing the first Gmail import…",
        )
    except JobQueueFull as exc:
        raise StateConflictError(
            code="BACKGROUND_QUEUE_FULL",
            message="GODFIN is already handling too much background work.",
            hint="Wait for the current work to finish, then try again.",
        ) from exc

    return {
        "success": True,
        "message": (
            "Initial sync started in background"
            if queued.created
            else "A Gmail import is already in progress"
        ),
        "job_id": queued.job_id,
        "started": queued.created,
        "already_running": not queued.created,
    }


@router.get(
    "/ingest/gmail/sync-status",
    response_model=IngestionProgressResponse,
    response_model_exclude_unset=True,
)
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

    payload = {
        "status": status,
        "processed": processed,
        "total": total,
        "percent": round((processed / total) * 100, 1) if total > 0 else 0,
        "result": parsed_result,
        "error": (values['sync_error'] or '').strip() or None,
    }
    try:
        job = latest_job(kind="gmail_initial_sync", active_key="gmail-ingestion")
    except Exception:
        job = None
    if job and job["kind"] == "gmail_initial_sync":
        payload["job_id"] = job["id"]
        payload["attempt"] = job["attempt"]
        payload["retry_at"] = job["retry_at"]
        if job["status"] in {"queued", "running", "retry_wait", "cancel_requested"}:
            payload["status"] = "running"
            payload["percent"] = job["progress"]
            payload["total"] = max(payload["total"], job["total"])
        elif job["status"] in {"failed", "poisoned"}:
            payload["status"] = "error"
            payload["error"] = job["message"]
        elif job["status"] == "cancelled":
            payload["status"] = "cancelled"
    return payload


@router.post(
    "/ingest/gmail/sync/cancel",
    response_model=BackgroundCancelResponse,
)
def cancel_initial_sync_background(
    _user: bool = Depends(get_current_user),
):
    job = latest_job(kind="gmail_initial_sync", active_key="gmail-ingestion")
    cancelled = bool(job and request_job_cancel(job["id"]))
    return {"cancel_requested": cancelled, "job_id": job["id"] if job else None}


# --- Ingest with Date Range ---

class DateRangeRequest(BaseModel):
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def validate_range(self):
        if self.start_date >= self.end_date:
            raise ValueError("Start date must be before end date")
        if self.end_date > date.today():
            raise ValueError("End date cannot be in the future")
        return self


@router.post(
    "/ingest/gmail/range",
    response_model=DateRangeIngestionResponse,
)
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

    start = request.start_date
    end = request.end_date

    try:
        # Convert to Gmail query format (before_date is exclusive)
        end_plus_one = (end + timedelta(days=1)).strftime('%Y-%m-%d')

        result = run_ingestion_with_dates(
            db,
            after_date=start.isoformat(),
            before_date=end_plus_one,
            is_manual=True
        )

        return {
            "success": True,
            "result": result.to_dict(),
            "date_range": f"{start.isoformat()} to {end.isoformat()}",
            "message": f"Ingestion complete. Processed {result.processed}, created {result.created}.",
        }
    except Exception as exc:
        raise IntegrationUnavailableError(
            code="GMAIL_INGESTION_FAILED",
            message="Gmail import could not be completed for that date range.",
            hint="Check the Gmail connection and try again.",
        ) from exc


# --- Background Date Range Ingestion ---

@router.post(
    "/ingest/gmail/range/start",
    response_model=BackgroundIngestionStartResponse,
)
def start_ingestion_range_background(
    request: DateRangeRequest,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """
    Kick off date-range ingestion as a background task. Returns immediately.
    Poll /ingest/gmail/range/status for progress.
    """
    if not is_connected():
        raise HTTPException(status_code=400, detail="Gmail not connected")

    start = request.start_date
    end = request.end_date

    # end_date is inclusive in the UI, so add 1 day for the query
    end_plus_one = (end + timedelta(days=1)).strftime('%Y-%m-%d')

    try:
        queued = enqueue_job(
            "gmail_date_range",
            payload={
                "start_date": start.isoformat(),
                "end_date": end_plus_one,
            },
            active_key="gmail-ingestion",
            max_attempts=3,
            public_message="Preparing the selected Gmail date range…",
        )
    except JobQueueFull as exc:
        raise StateConflictError(
            code="BACKGROUND_QUEUE_FULL",
            message="GODFIN is already handling too much background work.",
            hint="Wait for the current work to finish, then try again.",
        ) from exc

    return {
        "success": True,
        "message": (
            "Ingestion started"
            if queued.created
            else "A Gmail import is already in progress"
        ),
        "job_id": queued.job_id,
        "started": queued.created,
        "already_running": not queued.created,
    }


@router.get(
    "/ingest/gmail/range/status",
    response_model=RangeIngestionProgressResponse,
    response_model_exclude_unset=True,
)
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
            parsed_result = None

    payload = {
        "status": status,
        "processed": processed,
        "total": total,
        "batch_current": batch_current,
        "batch_total": batch_total,
        "percent": round((processed / total) * 100, 1) if total > 0 else 0,
        "result": parsed_result,
        "error": (values['ingest_now_error'] or '').strip() or None,
    }
    try:
        job = latest_job(kind="gmail_date_range", active_key="gmail-ingestion")
    except Exception:
        job = None
    if job and job["kind"] == "gmail_date_range":
        payload["job_id"] = job["id"]
        payload["attempt"] = job["attempt"]
        payload["retry_at"] = job["retry_at"]
        if job["status"] in {"queued", "running", "retry_wait", "cancel_requested"}:
            payload["status"] = "running"
            payload["percent"] = job["progress"]
            payload["total"] = max(payload["total"], job["total"])
        elif job["status"] in {"failed", "poisoned"}:
            payload["status"] = "error"
            payload["error"] = job["message"]
        elif job["status"] == "cancelled":
            payload["status"] = "cancelled"
    return payload


@router.post(
    "/ingest/gmail/range/cancel",
    response_model=BackgroundCancelResponse,
)
def cancel_ingestion_range_background(
    _user: bool = Depends(get_current_user),
):
    job = latest_job(kind="gmail_date_range", active_key="gmail-ingestion")
    cancelled = bool(job and request_job_cancel(job["id"]))
    return {"cancel_requested": cancelled, "job_id": job["id"] if job else None}


# --- Scheduler/History Status ---

@router.get("/ingest/scheduler/status", response_model=SchedulerStatusResponse)
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

@router.get("/ingest/settings", response_model=IngestSettingsResponse)
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


@router.post("/ingest/settings", response_model=IngestSettingsUpdateResponse)
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
