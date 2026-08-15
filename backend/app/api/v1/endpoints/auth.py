from __future__ import annotations

import re

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
from app.core.local_api_trust import RuntimeMode, runtime_mode
from app.core.pin_security import client_ip_from_request, require_current_pin
from app.models.app_setting import AppSetting
from app.schemas.auth import (
    AuthResponse,
    AuthStatusResponse,
    LogoutResponse,
    PinChange,
    PinSet,
    PinVerify,
)

router = APIRouter()

# PIN validation constants
MIN_PIN_LENGTH = 4
MAX_NEW_PIN_LENGTH = 6
MAX_LEGACY_PIN_LENGTH = 8
PIN_LENGTH_SETTING_KEY = "pin_length"


def _validate_pin_format(
    pin: str,
    *,
    allow_legacy_length: bool = False,
    reject_weak: bool = True,
) -> None:
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
    ascending = "01234567890123456789"
    descending = ascending[::-1]
    common_pins = {"1234", "4321", "1212", "2580", "0852", "6969"}
    repeated_pair = len(pin) in {4, 6} and pin == pin[:2] * (len(pin) // 2)
    year_like = len(pin) == 4 and 1900 <= int(pin) <= 2099
    weak = (
        len(set(pin)) == 1
        or pin in ascending
        or pin in descending
        or pin in common_pins
        or repeated_pair
        or year_like
    )
    if reject_weak and weak:
        raise HTTPException(status_code=400, detail="PIN is too simple. Avoid sequential or repeated digits.")


def _store_pin_length(db: Session, length: int) -> None:
    setting = db.query(AppSetting).filter_by(key=PIN_LENGTH_SETTING_KEY).first()
    if setting:
        setting.value = str(length)
    else:
        db.add(AppSetting(key=PIN_LENGTH_SETTING_KEY, value=str(length)))


def _stored_pin_length(db: Session) -> int | None:
    setting = db.query(AppSetting).filter_by(key=PIN_LENGTH_SETTING_KEY).first()
    if not setting:
        return None
    try:
        length = int(setting.value)
    except (TypeError, ValueError):
        return None
    return length if MIN_PIN_LENGTH <= length <= MAX_LEGACY_PIN_LENGTH else None


@router.get("/status", response_model=AuthStatusResponse)
def auth_status(db: Session = Depends(get_db)):
    setting = db.query(AppSetting).filter_by(key="is_first_run").first()
    is_first_run = setting.value == "true" if setting else True
    return AuthStatusResponse(
        is_first_run=is_first_run,
        pin_length=(
            None
            if is_first_run or runtime_mode() is RuntimeMode.LAN
            else _stored_pin_length(db)
        ),
    )


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
    _store_pin_length(db, len(body.pin))

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
        ip_address=client_ip_from_request(request),
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
    pin_setting = require_current_pin(
        db,
        body.current_pin,
        client_ip_from_request(request),
        action="change_pin",
        failure_detail="Current PIN is incorrect",
    )

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
    _store_pin_length(db, len(body.new_pin))
    db.commit()

    # Changing the PIN rotates the session identity and revokes every other
    # browser/device session.
    revoke_all_sessions(db)
    token = create_session(
        db,
        user_agent=request.headers.get("user-agent"),
        ip_address=client_ip_from_request(request),
    )
    db.commit()
    return AuthResponse(authenticated=True, token=token)


@router.post("/verify-pin", response_model=AuthResponse)
def verify_pin(body: PinVerify, request: Request, db: Session = Depends(get_db)):
    client_ip = client_ip_from_request(request)

    # Validate PIN format
    _validate_pin_format(body.pin, allow_legacy_length=True, reject_weak=False)
    require_current_pin(
        db,
        body.pin,
        client_ip,
        action="unlock",
        failure_status=401,
        failure_detail="Incorrect PIN",
        missing_status=400,
        missing_detail="No PIN set",
    )
    if _stored_pin_length(db) != len(body.pin):
        _store_pin_length(db, len(body.pin))
    token = create_session(
        db,
        user_agent=request.headers.get("user-agent"),
        ip_address=client_ip,
    )
    db.commit()
    return AuthResponse(authenticated=True, token=token)


@router.post("/logout", response_model=LogoutResponse)
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
