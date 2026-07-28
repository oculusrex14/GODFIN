from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.gmail_service import (
    gmail_service, disconnect_gmail, is_connected, handle_manual_oauth_code,
    CLIENT_SECRETS_FILE
)
from app.core.ingestion import (
    get_ingestion_history, run_ingestion, run_ingestion_with_dates,
    run_ingestion_with_dates_background,
    run_initial_sync, run_initial_sync_background,
)
from app.core.scheduler import _set_manual_ingestion_running
from app.models.app_setting import AppSetting

logger = logging.getLogger(__name__)
router = APIRouter()


def get_backend_url(request: Request) -> str:
    """Get the backend URL based on the request's host."""
    host = request.headers.get("host", "localhost:5100")
    return f"http://{host}"


def get_frontend_url(request: Request) -> str:
    """Get the frontend URL based on the request's origin."""
    origin = request.headers.get("origin") or request.headers.get("referer")
    if origin and origin.startswith("http"):
        parts = origin.split("/")
        if len(parts) >= 3:
            return f"{parts[0]}//{parts[2]}"
    return "http://localhost:5200"


# --- Gmail OAuth ---

@router.get("/auth/gmail/url")
def get_gmail_auth_url(
    request: Request,
    use_oob: bool = Query(False),
    _user: bool = Depends(get_current_user),
):
    """Get Gmail OAuth authorization URL.

    Args:
        use_oob: If True, use out-of-band flow (manual code entry).
                 Use this for mobile/network access where Google doesn't
                 allow private IP redirect URIs.
    """
    try:
        from app.core.gmail_service import CLIENT_SECRETS_FILE

        logger.info(f"Gmail auth URL requested, use_oob={use_oob}")

        if not CLIENT_SECRETS_FILE.exists():
            raise HTTPException(
                status_code=400,
                detail="Gmail client_secret.json not found in data/ directory",
            )

        # Check if ngrok is running
        ngrok_url = os.environ.get('NGROK_URL', None)
        frontend_url = get_frontend_url(request)

        logger.info(f"Frontend URL: {frontend_url}, ngrok_url: {ngrok_url}")

        # For network access, use ngrok URL if available
        if use_oob and ngrok_url:
            # Use ngrok URL for redirect
            redirect_uri = f"{ngrok_url}/api/v1/auth/gmail/callback"
            auth_url = gmail_service.get_auth_url(redirect_uri=redirect_uri)
            logger.info(f"Using ngrok redirect_uri: {redirect_uri}")
            return {"auth_url": auth_url, "flow": "redirect"}
        elif use_oob:
            # Fallback to OOB flow
            auth_url = gmail_service.get_auth_url(use_oob=True)
            return {
                "auth_url": auth_url,
                "flow": "manual",
                "instructions": "Open this URL in a browser, authorize, and enter the code shown."
            }
        else:
            # Standard redirect flow (for localhost)
            backend_url = get_backend_url(request)
            redirect_uri = f"{backend_url}/api/v1/auth/gmail/callback"
            auth_url = gmail_service.get_auth_url(redirect_uri=redirect_uri)
            logger.info(f"Using standard redirect flow: {redirect_uri}")

            # Append frontend_url for callback redirect
            if auth_url:
                if "?" in auth_url:
                    auth_url = f"{auth_url}&frontend_url={frontend_url}"
                else:
                    auth_url = f"{auth_url}?frontend_url={frontend_url}"

            return {"auth_url": auth_url, "flow": "redirect"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate auth URL: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate auth URL: {str(e)}")


@router.get("/auth/gmail/callback")
def gmail_oauth_callback(
    request: Request,
    code: str = Query(None),
    error: str = Query(None),
    frontend_url: str = Query("http://localhost:5200"),
):
    """
    Handle OAuth callback from Google.

    This endpoint is called by Google after user authorizes access.
    """
    # Validate frontend_url to prevent open redirect attacks
    # Only allow redirects to localhost or the configured frontend
    allowed_hosts = [
        'http://localhost:5200',
        'http://localhost:5173',
        'http://127.0.0.1:5200',
        'http://127.0.0.1:5173',
    ]
    # Also check for dynamic localhost variants
    is_localhost = (
        frontend_url.startswith('http://localhost') or
        frontend_url.startswith('http://127.0.0.1') or
        frontend_url.startswith('http://0.0.0.0')
    )
    # For production, you'd want to add your actual domain here
    if not is_localhost and frontend_url not in allowed_hosts:
        logger.warning(f"Blocked redirect to untrusted URL: {frontend_url}")
        frontend_url = "http://localhost:5200"

    if not frontend_url:
        frontend_url = "http://localhost:5200"

    if error:
        return RedirectResponse(
            url=f"{frontend_url}/settings?gmail_error={error}",
            status_code=302,
        )

    if not code:
        raise HTTPException(status_code=400, detail="No authorization code provided")

    try:
        # Get the redirect URI that was used for the auth request
        backend_url = get_backend_url(request)
        redirect_uri = f"{backend_url}/api/v1/auth/gmail/callback"

        logger.info(f"Completing auth with redirect_uri: {redirect_uri}")
        success = gmail_service.complete_auth(code, redirect_uri=redirect_uri)

        if success:
            return RedirectResponse(
                url=f"{frontend_url}/settings?gmail_connected=true",
                status_code=302,
            )
        else:
            return RedirectResponse(
                url=f"{frontend_url}/settings?gmail_error=auth_failed",
                status_code=302,
            )
    except Exception as e:
        logger.error(f"OAuth callback error: {e}")
        return RedirectResponse(
            url=f"{frontend_url}/settings?gmail_error={str(e)}",
            status_code=302,
        )


class GmailStatusResponse:
    pass


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

@router.post("/auth/gmail/disconnect")
def gmail_disconnect(
    clear_data: bool = False,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """
    Disconnect Gmail and optionally clear all Gmail-sourced transactions.
    """
    from app.models.transaction import Transaction
    from app.models.audit_log import AuditLog
    from app.models.transaction_split import TransactionSplit

    try:
        if not gmail_service.is_connected:
            return {"success": True, "message": "Gmail was not connected"}

        # Clear Gmail-sourced transactions if requested
        deleted_count = 0
        if clear_data:
            try:
                # Use raw SQL to handle cascade deletion properly
                # First delete audit logs referencing affected transactions
                db.execute(text("""
                    DELETE FROM audit_log
                    WHERE transaction_id IN (
                        SELECT id FROM transactions
                        WHERE source IN ('gmail', 'statement_upload', 'statement')
                    )
                """))

                # Delete transaction splits referencing affected transactions
                db.execute(text("""
                    DELETE FROM transaction_splits
                    WHERE parent_transaction_id IN (
                        SELECT id FROM transactions
                        WHERE source IN ('gmail', 'statement_upload', 'statement')
                    )
                """))

                # Delete all user transactions (gmail + statement uploads)
                result = db.execute(text("""
                    DELETE FROM transactions
                    WHERE source IN ('gmail', 'statement_upload', 'statement')
                """))
                deleted_count = result.rowcount

                db.commit()
            except Exception as e:
                db.rollback()
                logger.error(f"Failed to delete Gmail transactions: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to delete transactions: {str(e)}")

        # Clear ingestion settings
        try:
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
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to clear ingestion settings: {e}")

        # Revoke credentials
        try:
            success = gmail_service.disconnect()
        except Exception as e:
            logger.error(f"Failed to disconnect Gmail service: {e}")
            # Still return success if we got this far, as we cleared the data
            success = True

        if success:
            message = "Gmail disconnected successfully"
            if clear_data and deleted_count:
                message += f". {deleted_count} transactions removed."
            return {"success": True, "message": message}
        else:
            raise HTTPException(status_code=500, detail="Failed to disconnect Gmail")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in gmail_disconnect: {e}")
        raise HTTPException(status_code=500, detail=f"Disconnect failed: {str(e)}")


# --- Manual OAuth Code Entry ---

@router.post("/auth/gmail/manual-code")
def gmail_manual_code(
    code: str,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """
    Handle OAuth code from manual copy-paste (for headless environments).
    """
    success, message = handle_manual_oauth_code(code)
    if success:
        return {"success": True, "connected": True, "message": message}
    else:
        raise HTTPException(status_code=400, detail=message)


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
    status = raw_status if raw_status in ('running', 'completed', 'error') else 'idle'

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

    return {
        "status": status,
        "processed": processed,
        "total": total,
        "percent": round((processed / total) * 100, 1) if total > 0 else 0,
        "result": result_val or None,
        "error": (values['sync_error'] or '').strip() or None,
    }


# --- Ingest with Date Range ---

from pydantic import BaseModel


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
    status = raw_status if raw_status in ('running', 'completed', 'error') else 'idle'

    result_val = (values['ingest_now_result'] or '').strip()

    # Parse result string back to dict if completed
    parsed_result = None
    if status == 'completed' and result_val:
        try:
            import ast
            parsed_result = ast.literal_eval(result_val)
        except Exception:
            parsed_result = result_val

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


from pydantic import BaseModel


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
