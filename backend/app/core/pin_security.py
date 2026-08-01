"""Shared, persistent PIN verification and throttling for every sensitive action."""

from __future__ import annotations

import ipaddress
import os
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request
from sqlalchemy import case
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.core.auth import hash_pin, pin_hash_needs_upgrade, verify_pin_hash
from app.models.app_setting import AppSetting
from app.models.pin_attempt import PinAttempt


RATE_LIMIT_MAX_ATTEMPTS = 5
RATE_LIMIT_WINDOW_SECONDS = 300
LOCAL_DEVICE_SCOPE = "__local_device__"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def client_ip_from_request(request: Request) -> str:
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


def _scope_keys(client_ip: str) -> tuple[str, ...]:
    # Retain the original raw-IP key so existing persisted counters continue
    # to apply after this shared local-device throttle is introduced.
    return (LOCAL_DEVICE_SCOPE, client_ip[:64])


def check_pin_rate_limit(db: Session, client_ip: str) -> None:
    now = _utcnow()
    attempts = (
        db.query(PinAttempt)
        .filter(PinAttempt.client_ip.in_(_scope_keys(client_ip)))
        .all()
    )
    retry_after = 0
    stale_keys: list[str] = []
    for attempt in attempts:
        if attempt.blocked_until and attempt.blocked_until > now:
            retry_after = max(
                retry_after,
                max(1, int((attempt.blocked_until - now).total_seconds())),
            )
        elif now - attempt.window_started_at >= timedelta(
            seconds=RATE_LIMIT_WINDOW_SECONDS
        ):
            stale_keys.append(attempt.client_ip)
    if retry_after:
        raise HTTPException(
            status_code=429,
            detail="Too many failed PIN attempts. Please try again later.",
            headers={"Retry-After": str(retry_after)},
        )
    if stale_keys:
        db.query(PinAttempt).filter(PinAttempt.client_ip.in_(stale_keys)).delete(
            synchronize_session=False
        )
        db.commit()


def record_failed_pin_attempt(db: Session, client_ip: str) -> None:
    """Atomically increment both device-global and source-IP counters."""
    now = _utcnow()
    window_cutoff = now - timedelta(seconds=RATE_LIMIT_WINDOW_SECONDS)
    blocked_until = now + timedelta(seconds=RATE_LIMIT_WINDOW_SECONDS)
    for scope_key in _scope_keys(client_ip):
        expired = PinAttempt.window_started_at <= window_cutoff
        statement = sqlite_insert(PinAttempt).values(
            client_ip=scope_key,
            failed_attempts=1,
            window_started_at=now,
            blocked_until=None,
            updated_at=now,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[PinAttempt.client_ip],
            set_={
                "failed_attempts": case(
                    (expired, 1),
                    else_=PinAttempt.failed_attempts + 1,
                ),
                "window_started_at": case(
                    (expired, now),
                    else_=PinAttempt.window_started_at,
                ),
                "blocked_until": case(
                    (expired, None),
                    (
                        PinAttempt.failed_attempts + 1 >= RATE_LIMIT_MAX_ATTEMPTS,
                        blocked_until,
                    ),
                    else_=PinAttempt.blocked_until,
                ),
                "updated_at": now,
            },
        )
        db.execute(statement)
    db.commit()


def clear_failed_pin_attempts(db: Session, client_ip: str) -> None:
    db.query(PinAttempt).filter(
        PinAttempt.client_ip.in_(_scope_keys(client_ip))
    ).delete(synchronize_session=False)
    db.commit()


def require_current_pin(
    db: Session,
    pin: str | None,
    client_ip: str,
    *,
    failure_status: int = 403,
    failure_detail: str = "Incorrect PIN",
    missing_status: int = 403,
    missing_detail: str = "Enter your current PIN to continue",
) -> AppSetting:
    """Verify and transparently upgrade a PIN under the shared throttle."""
    check_pin_rate_limit(db, client_ip)
    if not pin:
        raise HTTPException(status_code=missing_status, detail=missing_detail)
    pin_setting = db.query(AppSetting).filter_by(key="pin_hash").first()
    if not pin_setting or not pin_setting.value:
        raise HTTPException(status_code=400, detail="No PIN set")
    if not verify_pin_hash(pin, pin_setting.value):
        record_failed_pin_attempt(db, client_ip)
        raise HTTPException(status_code=failure_status, detail=failure_detail)

    if pin_hash_needs_upgrade(pin_setting.value):
        pin_setting.value = hash_pin(pin)
    clear_failed_pin_attempts(db, client_ip)
    return pin_setting
