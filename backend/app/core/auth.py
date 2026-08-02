from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.session import AuthSession

# Kept as a compatibility shim for older test fixtures. Session validation is
# database-backed; this dictionary is never authoritative.
_active_tokens: dict[str, tuple[float, float]] = {}

TOKEN_EXPIRY_SECONDS = int(os.environ.get("GODFIN_SESSION_TTL_SECONDS", 30 * 24 * 60 * 60))
MAX_ACTIVE_SESSIONS = int(os.environ.get("GODFIN_MAX_SESSIONS", 3))
LEGACY_TOKEN_KEY = "auth_token"
PIN_HASH_ALGORITHM = "pbkdf2-sha256"
PIN_HASH_VERSION = 1
PIN_HASH_ITERATIONS = 600_000
LEGACY_PIN_HASH_ITERATIONS = 100_000
PIN_HASH_USABILITY_BUDGET_SECONDS = 2.0


def _utcnow() -> datetime:
    # SQLite stores a timezone-naive value. Treat every persisted value as UTC.
    return datetime.now(timezone.utc).replace(tzinfo=None)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hash_pin(pin: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        pin.encode(),
        salt,
        PIN_HASH_ITERATIONS,
    )
    return (
        f"{PIN_HASH_ALGORITHM}${PIN_HASH_VERSION}${PIN_HASH_ITERATIONS}"
        f"${salt.hex()}${digest.hex()}"
    )


def verify_pin_hash(pin: str, stored: str) -> bool:
    if not stored:
        return False
    iterations = LEGACY_PIN_HASH_ITERATIONS
    try:
        if stored.startswith(f"{PIN_HASH_ALGORITHM}$"):
            algorithm, version_text, iterations_text, salt_hex, hash_hex = stored.split(
                "$",
                4,
            )
            if algorithm != PIN_HASH_ALGORITHM or int(version_text) != PIN_HASH_VERSION:
                return False
            iterations = int(iterations_text)
            if not 100_000 <= iterations <= 2_000_000:
                return False
        elif ":" in stored:
            salt_hex, hash_hex = stored.split(":", 1)
        else:
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
        if len(salt) != 16 or len(expected) != 32:
            return False
    except (TypeError, ValueError):
        return False
    actual = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, iterations)
    return hmac.compare_digest(actual, expected)


def pin_hash_needs_upgrade(stored: str) -> bool:
    """Return True for legacy or weaker versioned PIN hashes."""
    if not stored.startswith(f"{PIN_HASH_ALGORITHM}$"):
        return True
    try:
        algorithm, version_text, iterations_text, _salt, _digest = stored.split("$", 4)
        return (
            algorithm != PIN_HASH_ALGORITHM
            or int(version_text) != PIN_HASH_VERSION
            or int(iterations_text) < PIN_HASH_ITERATIONS
        )
    except (TypeError, ValueError):
        return True


def purge_expired_sessions(db: Session, *, now: Optional[datetime] = None) -> int:
    current = now or _utcnow()
    deleted = (
        db.query(AuthSession)
        .filter(AuthSession.expires_at <= current)
        .delete(synchronize_session=False)
    )
    return int(deleted or 0)


def revoke_all_sessions(db: Session) -> int:
    deleted = db.query(AuthSession).delete(synchronize_session=False)
    return int(deleted or 0)


def create_session(
    db: Session,
    *,
    user_agent: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> str:
    """Create a hashed, expiring session and enforce the configured cap."""
    now = _utcnow()
    purge_expired_sessions(db, now=now)

    active = (
        db.query(AuthSession)
        .order_by(AuthSession.created_at.asc(), AuthSession.id.asc())
        .all()
    )
    overflow = max(0, len(active) - MAX_ACTIVE_SESSIONS + 1)
    for session in active[:overflow]:
        db.delete(session)

    token = secrets.token_urlsafe(32)
    db.add(
        AuthSession(
            token_hash=hash_token(token),
            created_at=now,
            expires_at=now + timedelta(seconds=TOKEN_EXPIRY_SECONDS),
            last_seen_at=now,
            user_agent=(user_agent or "")[:500] or None,
            ip_address=(ip_address or "")[:64] or None,
        )
    )
    db.flush()
    return token


def validate_token(db: Session, token: str) -> bool:
    if not token:
        return False
    session = db.query(AuthSession).filter_by(token_hash=hash_token(token)).first()
    if session is None:
        return False

    now = _utcnow()
    if session.expires_at <= now:
        db.delete(session)
        db.commit()
        return False

    # Avoid a disk write on every API call while still keeping useful activity.
    if session.last_seen_at <= now - timedelta(minutes=5):
        session.last_seen_at = now
        db.commit()
    return True


def revoke_token(db: Session, token: str) -> bool:
    session = db.query(AuthSession).filter_by(token_hash=hash_token(token)).first()
    if session is None:
        return False
    db.delete(session)
    db.flush()
    return True


def remove_legacy_plaintext_token(db: Session) -> None:
    """Remove the pre-Phase-0 plaintext token without ever loading it."""
    from app.models.app_setting import AppSetting

    setting = db.query(AppSetting).filter_by(key=LEGACY_TOKEN_KEY).first()
    if setting:
        db.delete(setting)
        db.commit()


def load_token_from_db(db: Session) -> None:
    """Backward-compatible startup hook.

    The legacy token is intentionally discarded; new sessions already live in
    the sessions table and require no in-memory restore step.
    """
    remove_legacy_plaintext_token(db)
    if purge_expired_sessions(db):
        db.commit()


def get_current_user(
    authorization: str = Header(default=""),
    db: Session = Depends(get_db),
) -> bool:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization[7:]
    if not validate_token(db, token):
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return True
