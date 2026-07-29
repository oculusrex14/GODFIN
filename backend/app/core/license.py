from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.encryption import SecretDecryptionError, decrypt, encrypt
from app.core.entitlements import (
    features_for_tier,
    included_hosted_ai_credits,
)
from app.models.app_setting import AppSetting

LICENSE_KEY_PATTERN = re.compile(
    r"^GODFIN-(PRO|MAX)-[A-Z0-9]{5}(?:-[A-Z0-9]{5}){4}$"
)
LICENSE_FEATURES = {
    tier: features_for_tier(tier) for tier in ("free", "pro", "max")
}
_SENSITIVE_KEYS = {"license_key"}
_INSTALLATION_KEYCHAIN_SERVICE = "com.godfin.desktop"
_INSTALLATION_KEYCHAIN_ACCOUNT = "installation-id"


class LicenseError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "LICENSE_ERROR",
        status_code: int = 400,
        retriable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.retriable = retriable


def _machine_id_path() -> Path:
    configured = os.environ.get("GODFIN_MACHINE_ID_FILE")
    if configured:
        return Path(configured).expanduser()
    return Path(__file__).resolve().parents[2] / "data" / ".machine_id"


def _installation_keychain_enabled() -> bool:
    return (
        platform.system() == "Darwin"
        and os.environ.get("GODFIN_DISABLE_KEYCHAIN", "").lower()
        not in {"1", "true", "yes"}
    )


def _read_installation_id_from_keychain() -> str | None:
    if not _installation_keychain_enabled():
        return None
    try:
        result = subprocess.run(
            [
                "security",
                "find-generic-password",
                "-a",
                _INSTALLATION_KEYCHAIN_ACCOUNT,
                "-s",
                _INSTALLATION_KEYCHAIN_SERVICE,
                "-w",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = result.stdout.strip()
    return value if value else None


def _store_installation_id_in_keychain(value: str) -> bool:
    if not _installation_keychain_enabled():
        return False
    try:
        subprocess.run(
            [
                "security",
                "add-generic-password",
                "-U",
                "-a",
                _INSTALLATION_KEYCHAIN_ACCOUNT,
                "-s",
                _INSTALLATION_KEYCHAIN_SERVICE,
                "-w",
                value,
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return True


def _store_installation_id_in_file(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(descriptor, f"{value}\n".encode())
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.chmod(path, 0o600)


def get_machine_id() -> str:
    """Return an anonymous, installation-scoped identifier.

    A random token is used instead of hardware identifiers so license checks
    never disclose a serial number, hostname, username, or financial data.
    """
    configured_path = bool(os.environ.get("GODFIN_MACHINE_ID_FILE"))
    path = _machine_id_path()
    if not configured_path:
        keychain_value = _read_installation_id_from_keychain()
        if keychain_value:
            return keychain_value

    if path.exists():
        value = path.read_text(encoding="utf-8").strip()
        if value:
            if not configured_path and _store_installation_id_in_keychain(value):
                return value
            return value

    value = str(uuid.uuid4())
    if not configured_path and _store_installation_id_in_keychain(value):
        return value
    _store_installation_id_in_file(path, value)
    return value


def get_device_label() -> str:
    system = platform.system() or "Unknown OS"
    system_labels = {
        "Darwin": "macOS",
        "Windows": "Windows",
        "Linux": "Linux",
    }
    architecture = platform.machine() or "unknown architecture"
    return f"{system_labels.get(system, system)} {architecture}"[:80]


def _get(db: Session, key: str, default: str = "") -> str:
    setting = db.query(AppSetting).filter_by(key=key).first()
    return setting.value if setting else default


def _set(db: Session, key: str, value: str) -> None:
    setting = db.query(AppSetting).filter_by(key=key).first()
    if setting:
        setting.value = value
    else:
        db.add(AppSetting(key=key, value=value))


def _parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def normalize_license_key(value: str) -> str:
    return re.sub(r"\s+", "", value.strip().upper())


def _masked_key(db: Session) -> str | None:
    encrypted_key = _get(db, "license_key")
    if not encrypted_key:
        return None
    try:
        key = decrypt(encrypted_key)
    except SecretDecryptionError:
        return "GODFIN-••••"
    return f"{key[:10]}-••••-••••-{key[-5:]}"


def license_status(db: Session, *, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    tier = _get(db, "license_tier", "free")
    stored_status = _get(db, "license_status", "inactive")
    verified_at = _parse_datetime(_get(db, "license_verified_at"))
    grace_deadline = (
        verified_at + timedelta(days=settings.LICENSE_OFFLINE_GRACE_DAYS)
        if verified_at
        else None
    )
    active = (
        tier in {"pro", "max"}
        and stored_status == "active"
        and grace_deadline is not None
        and now <= grace_deadline
    )

    if active:
        effective_tier = tier
        status = "active"
        message = (
            f"GODFIN {tier.title()} is active. Verification remains valid "
            f"offline through {grace_deadline.date().isoformat()}."
        )
    elif tier in {"pro", "max"} and stored_status == "active":
        effective_tier = "free"
        status = "verification_required"
        message = "Reconnect to verify this license and restore paid features."
    else:
        effective_tier = "free"
        status = stored_status if stored_status not in {"", "active"} else "inactive"
        message = "GODFIN Core is active. Enter a license key to unlock Pro features."

    return {
        "tier": effective_tier,
        "licensed_tier": tier if tier in {"pro", "max"} else None,
        "status": status,
        "valid": active,
        "features": LICENSE_FEATURES[effective_tier],
        "verified_at": verified_at.isoformat() if verified_at else None,
        "offline_grace_until": grace_deadline.isoformat() if grace_deadline else None,
        "monthly_credits": included_hosted_ai_credits(),
        "hosted_credits_included": included_hosted_ai_credits(),
        "topup_credits": int(_get(db, "license_topup_credits", "0") or 0)
        if active
        else 0,
        "masked_key": _masked_key(db),
        "message": message,
        "website_url": settings.WEBSITE_URL.rstrip("/"),
    }


def has_feature(db: Session, feature: str) -> bool:
    return feature in license_status(db)["features"]


def require_feature(db: Session, feature: str) -> None:
    if has_feature(db, feature):
        return
    raise LicenseError(
        "This feature requires an active GODFIN Pro or Max lifetime license.",
        code="LICENSE_REQUIRED",
        status_code=403,
    )


def _validate_server_response(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise LicenseError(
            "The license server returned an invalid response.",
            code="VERIFY_INVALID_RESPONSE",
            status_code=502,
            retriable=True,
        )
    if payload.get("valid") is not True:
        raise LicenseError(
            str(payload.get("message") or "License verification failed."),
            code=str(payload.get("code") or "LICENSE_INVALID"),
            status_code=403,
        )
    tier = payload.get("tier")
    if tier not in {"pro", "max"}:
        raise LicenseError(
            "The license server returned an unknown tier.",
            code="VERIFY_INVALID_RESPONSE",
            status_code=502,
            retriable=True,
        )
    return {
        "tier": tier,
        "monthly_credits": included_hosted_ai_credits(),
        "topup_credits": max(0, int(payload.get("topup_credits") or 0)),
    }


def verify_with_server(license_key: str) -> dict[str, Any]:
    key = normalize_license_key(license_key)
    if not LICENSE_KEY_PATTERN.fullmatch(key):
        raise LicenseError(
            "Enter a valid GODFIN Pro or Max license key.",
            code="LICENSE_KEY_FORMAT",
            status_code=400,
        )
    try:
        response = httpx.post(
            settings.LICENSE_API_URL,
            json={
                "license_key": key,
                "machine_id": get_machine_id(),
                "device_label": get_device_label(),
                "app_version": settings.VERSION,
            },
            headers={"User-Agent": f"GODFIN/{settings.VERSION}"},
            timeout=httpx.Timeout(10.0, connect=5.0),
            follow_redirects=False,
        )
    except httpx.HTTPError as exc:
        raise LicenseError(
            "The license server is unavailable. Check your connection and try again.",
            code="VERIFY_UNAVAILABLE",
            status_code=503,
            retriable=True,
        ) from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise LicenseError(
            "The license server returned an invalid response.",
            code="VERIFY_INVALID_RESPONSE",
            status_code=502,
            retriable=True,
        ) from exc
    if response.status_code >= 500:
        raise LicenseError(
            str(payload.get("message") or "The license server is unavailable."),
            code=str(payload.get("code") or "VERIFY_UNAVAILABLE"),
            status_code=503,
            retriable=True,
        )
    return _validate_server_response(payload)


def activate_license(db: Session, license_key: str) -> dict[str, Any]:
    key = normalize_license_key(license_key)
    verified = verify_with_server(key)
    _set(db, "license_key", encrypt(key))
    _set(db, "license_tier", verified["tier"])
    _set(db, "license_status", "active")
    _set(db, "license_verified_at", datetime.now(UTC).isoformat())
    _set(db, "license_monthly_credits", str(verified["monthly_credits"]))
    _set(db, "license_topup_credits", str(verified["topup_credits"]))
    db.commit()
    return license_status(db)


def reverify_license(db: Session) -> dict[str, Any]:
    encrypted_key = _get(db, "license_key")
    if not encrypted_key:
        raise LicenseError(
            "No license key is stored on this device.",
            code="LICENSE_NOT_ACTIVATED",
            status_code=404,
        )
    try:
        key = decrypt(encrypted_key)
    except SecretDecryptionError as exc:
        _set(db, "license_status", "decrypt_failed")
        db.commit()
        raise LicenseError(
            "The stored license key cannot be decrypted. Enter it again.",
            code="LICENSE_DECRYPT_FAILED",
            status_code=409,
        ) from exc
    return activate_license(db, key)


def deactivate_license(db: Session) -> dict[str, Any]:
    for key, value in {
        "license_key": "",
        "license_tier": "free",
        "license_status": "inactive",
        "license_verified_at": "",
        "license_monthly_credits": "0",
        "license_topup_credits": "0",
    }.items():
        _set(db, key, value)
    db.commit()
    return license_status(db)
