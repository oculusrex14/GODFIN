from __future__ import annotations

import ipaddress
import os
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.auth import (
    create_session,
    get_current_user,
    hash_pin,
    revoke_all_sessions,
    revoke_token,
    verify_pin_hash,
)
from app.core.database import get_db
from app.models.app_setting import AppSetting
from app.models.pin_attempt import PinAttempt
from app.schemas.auth import AuthResponse, AuthStatusResponse, PinChange, PinSet, PinVerify

router = APIRouter()

RATE_LIMIT_MAX_ATTEMPTS = 5  # Max failed attempts
RATE_LIMIT_WINDOW_SECONDS = 300  # 5 minute window

# PIN validation constants
MIN_PIN_LENGTH = 4
MAX_NEW_PIN_LENGTH = 6
MAX_LEGACY_PIN_LENGTH = 8


def _validate_pin_format(pin: str, *, allow_legacy_length: bool = False) -> None:
    """Validate PIN format. Raises HTTPException if invalid."""
    max_length = MAX_LEGACY_PIN_LENGTH if allow_legacy_length else MAX_NEW_PIN_LENGTH
    if not pin:
        raise HTTPException(status_code=400, detail="PIN cannot be empty")
    if not re.match(r'^\d+$', pin):
        raise HTTPException(status_code=400, detail="PIN must contain only digits")
    if len(pin) < MIN_PIN_LENGTH:
        raise HTTPException(status_code=400, detail=f"PIN must be at least {MIN_PIN_LENGTH} digits")
    if len(pin) > max_length:
        raise HTTPException(status_code=400, detail=f"PIN cannot exceed {max_length} digits")
    # Reject weak PINs (sequential or repeated digits)
    weak_pins = ['2345', '3456', '4567', '5678', '6789', '7890',
                 '1111', '2222', '3333', '4444', '5555', '6666', '7777', '8888', '9999', '0000']
    if pin in weak_pins:
        raise HTTPException(status_code=400, detail="PIN is too simple. Avoid sequential or repeated digits.")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _client_ip(request: Request) -> str:
    direct_ip = request.client.host if request.client else "unknown"
    trusted = {
        value.strip()
        for value in os.environ.get("GODFIN_TRUSTED_PROXIES", "").split(",")
        if value.strip()
    }
    if direct_ip in trusted:
        forwarded = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
        if forwarded:
            try:
                return str(ipaddress.ip_address(forwarded))
            except ValueError:
                pass
    return direct_ip[:64]


def _check_rate_limit(db: Session, client_ip: str) -> None:
    attempt = db.query(PinAttempt).filter_by(client_ip=client_ip).first()
    if attempt is None:
        return
    now = _utcnow()
    if attempt.blocked_until and attempt.blocked_until > now:
        retry_after = max(1, int((attempt.blocked_until - now).total_seconds()))
        raise HTTPException(
            status_code=429,
            detail="Too many failed attempts. Please try again later.",
            headers={"Retry-After": str(retry_after)},
        )
    if now - attempt.window_started_at >= timedelta(seconds=RATE_LIMIT_WINDOW_SECONDS):
        db.delete(attempt)
        db.commit()


def _record_failed_attempt(db: Session, client_ip: str) -> None:
    now = _utcnow()
    attempt = db.query(PinAttempt).filter_by(client_ip=client_ip).first()
    if attempt is None:
        attempt = PinAttempt(
            client_ip=client_ip,
            failed_attempts=1,
            window_started_at=now,
            updated_at=now,
        )
        db.add(attempt)
    elif now - attempt.window_started_at >= timedelta(seconds=RATE_LIMIT_WINDOW_SECONDS):
        attempt.failed_attempts = 1
        attempt.window_started_at = now
        attempt.blocked_until = None
        attempt.updated_at = now
    else:
        attempt.failed_attempts += 1
        attempt.updated_at = now

    if attempt.failed_attempts >= RATE_LIMIT_MAX_ATTEMPTS:
        attempt.blocked_until = now + timedelta(seconds=RATE_LIMIT_WINDOW_SECONDS)
    db.commit()


def _clear_failed_attempts(db: Session, client_ip: str) -> None:
    db.query(PinAttempt).filter_by(client_ip=client_ip).delete(
        synchronize_session=False
    )
    db.commit()


@router.get("/status", response_model=AuthStatusResponse)
def auth_status(db: Session = Depends(get_db)):
    setting = db.query(AppSetting).filter_by(key="is_first_run").first()
    is_first_run = setting.value == "true" if setting else True
    return AuthStatusResponse(is_first_run=is_first_run)


@router.post("/set-pin", response_model=AuthResponse)
def set_pin(body: PinSet, request: Request, db: Session = Depends(get_db)):
    first_run = db.query(AppSetting).filter_by(key="is_first_run").first()
    if not first_run or first_run.value != "true":
        raise HTTPException(status_code=400, detail="PIN already set")

    # Validate PIN format
    _validate_pin_format(body.pin)

    pin_setting = db.query(AppSetting).filter_by(key="pin_hash").first()
    if pin_setting:
        pin_setting.value = hash_pin(body.pin)
    else:
        db.add(AppSetting(key="pin_hash", value=hash_pin(body.pin)))

    first_run.value = "false"
    onboarding_completed = (
        db.query(AppSetting).filter_by(key="onboarding_completed").first()
    )
    if onboarding_completed:
        onboarding_completed.value = "false"
    else:
        db.add(AppSetting(key="onboarding_completed", value="false"))
    onboarding_step = db.query(AppSetting).filter_by(key="onboarding_step").first()
    if onboarding_step:
        onboarding_step.value = "1"
    else:
        db.add(AppSetting(key="onboarding_step", value="1"))
    db.commit()

    token = create_session(
        db,
        user_agent=request.headers.get("user-agent"),
        ip_address=_client_ip(request),
    )
    db.commit()
    return AuthResponse(authenticated=True, token=token)


@router.post("/change-pin", response_model=AuthResponse)
def change_pin(
    body: PinChange,
    request: Request,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    pin_setting = db.query(AppSetting).filter_by(key="pin_hash").first()
    if not pin_setting or not pin_setting.value:
        raise HTTPException(status_code=400, detail="No PIN set")

    if not verify_pin_hash(body.current_pin, pin_setting.value):
        raise HTTPException(status_code=400, detail="Current PIN is incorrect")

    # Validate new PIN format
    _validate_pin_format(body.new_pin)

    # Check PIN history to prevent reuse
    PIN_HISTORY_KEY = "pin_history"
    MAX_HISTORY = 3

    pin_history_setting = db.query(AppSetting).filter_by(key=PIN_HISTORY_KEY).first()
    if pin_history_setting and pin_history_setting.value:
        try:
            import json
            pin_history = json.loads(pin_history_setting.value)
            # Check if new PIN matches any in history
            for old_pin_hash in pin_history:
                if verify_pin_hash(body.new_pin, old_pin_hash):
                    raise HTTPException(
                        status_code=400,
                        detail="Cannot reuse a recent PIN. Please choose a different PIN."
                    )
        except json.JSONDecodeError:
            pass  # If corrupted, skip history check

    # Hash current PIN before adding to history
    current_pin_hash = pin_setting.value

    # Update PIN history
    if pin_history_setting:
        try:
            import json
            pin_history = json.loads(pin_history_setting.value) if pin_history_setting.value else []
        except json.JSONDecodeError:
            pin_history = []
        pin_history.append(current_pin_hash)
        # Keep only last MAX_HISTORY PINs
        pin_history = pin_history[-MAX_HISTORY:]
        pin_history_setting.value = json.dumps(pin_history)
    else:
        import json
        db.add(AppSetting(key=PIN_HISTORY_KEY, value=json.dumps([current_pin_hash])))

    pin_setting.value = hash_pin(body.new_pin)
    db.commit()

    # Changing the PIN rotates the session identity and revokes every other
    # browser/device session.
    revoke_all_sessions(db)
    token = create_session(
        db,
        user_agent=request.headers.get("user-agent"),
        ip_address=_client_ip(request),
    )
    db.commit()
    return AuthResponse(authenticated=True, token=token)


@router.post("/verify-pin", response_model=AuthResponse)
def verify_pin(body: PinVerify, request: Request, db: Session = Depends(get_db)):
    client_ip = _client_ip(request)
    _check_rate_limit(db, client_ip)

    # Validate PIN format
    _validate_pin_format(body.pin, allow_legacy_length=True)

    pin_setting = db.query(AppSetting).filter_by(key="pin_hash").first()
    if not pin_setting or not pin_setting.value:
        raise HTTPException(status_code=400, detail="No PIN set")

    if not verify_pin_hash(body.pin, pin_setting.value):
        _record_failed_attempt(db, client_ip)
        raise HTTPException(status_code=401, detail="Incorrect PIN")

    _clear_failed_attempts(db, client_ip)
    token = create_session(
        db,
        user_agent=request.headers.get("user-agent"),
        ip_address=client_ip,
    )
    db.commit()
    return AuthResponse(authenticated=True, token=token)


@router.post("/logout")
def logout(
    authorization: str = Header(default=""),
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Logout endpoint that invalidates the current token."""
    if authorization.startswith("Bearer "):
        token = authorization[7:]
        revoke_token(db, token)
        db.commit()

    return {"status": "logged_out"}
