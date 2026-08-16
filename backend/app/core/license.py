from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import sys
import uuid
from datetime import UTC, datetime
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
from app.core.license_entitlement import (
    EntitlementValidationError,
    verify_entitlement_envelope,
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
_PACKAGED_LICENSE_ENDPOINTS = (
    "https://godfin.dev/api/license/verify",
    "https://godfin.vercel.app/api/license/verify",
)


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
        self.public_message = message


_AUTHORITATIVE_LICENSE_ERRORS = {
    "LICENSE_NOT_FOUND": "This license key was not found.",
    "LICENSE_INVALID": "This license could not be verified.",
    "LICENSE_REVOKED": "This license is no longer active.",
    "LICENSE_SUSPENDED": "This license is temporarily suspended.",
    "ACTIVATION_LIMIT": (
        "This license is already active on three devices. "
        "Deactivate one in your account and try again."
    ),
    "DEVICE_LIMIT_REACHED": (
        "This license is already active on three devices. "
        "Deactivate one in your account and try again."
    ),
    "DEVICE_LIMIT": (
        "This license is already active on three devices. "
        "Deactivate one in your account and try again."
    ),
    "INVALID_REQUEST": "The license request is invalid.",
}


def _authoritative_license_error(payload: dict[str, Any]) -> LicenseError:
    supplied_code = payload.get("code")
    code = (
        supplied_code
        if isinstance(supplied_code, str)
        and supplied_code in _AUTHORITATIVE_LICENSE_ERRORS
        else "LICENSE_INVALID"
    )
    return LicenseError(
        _AUTHORITATIVE_LICENSE_ERRORS[code],
        code=code,
        status_code=403,
    )


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
    raw_envelope = _get(db, "license_entitlement")
    claims: dict[str, Any] | None = None
    integrity_code: str | None = None
    if raw_envelope:
        try:
            envelope = json.loads(raw_envelope)
            claims = verify_entitlement_envelope(
                envelope,
                machine_id=get_machine_id(),
                now=now,
            )
        except (json.JSONDecodeError, EntitlementValidationError) as exc:
            integrity_code = getattr(exc, "code", "LICENSE_ENTITLEMENT_INVALID")

    if claims is not None:
        effective_tier = str(claims["tier"])
        status = "active"
        verified_at = _parse_datetime(str(claims["issued_at"]))
        grace_deadline = _parse_datetime(str(claims["expires_at"]))
        message = (
            f"GODFIN {effective_tier.title()} is active. Verification remains valid "
            f"offline through {grace_deadline.date().isoformat()}."
        )
        features = list(claims["features"])
        licensed_tier: str | None = effective_tier
        active = True
    elif raw_envelope:
        effective_tier = "free"
        status = (
            "verification_required"
            if integrity_code == "LICENSE_ENTITLEMENT_EXPIRED"
            else "invalid"
        )
        message = (
            "Reconnect to verify this license and restore paid features."
            if status == "verification_required"
            else "The stored signed license is invalid. Re-enter the license key."
        )
        verified_at = None
        grace_deadline = None
        features = LICENSE_FEATURES["free"]
        licensed_tier = None
        active = False
    else:
        effective_tier = "free"
        stored_status = _get(db, "license_status")
        has_stored_key = bool(_get(db, "license_key"))
        if has_stored_key and stored_status in {
            "revoked",
            "suspended",
            "activation_limit",
        }:
            status = stored_status
            message = {
                "revoked": "This license is no longer active.",
                "suspended": "This license is temporarily suspended.",
                "activation_limit": (
                    "This license is active on three other devices. "
                    "Deactivate one in your account and verify again."
                ),
            }[status]
        else:
            status = "verification_required" if has_stored_key else "inactive"
            message = (
                "Reconnect to verify this license and restore paid features."
                if status == "verification_required"
                else "GODFIN Core is active. Enter a license key to unlock Pro features."
            )
        verified_at = None
        grace_deadline = None
        features = LICENSE_FEATURES["free"]
        licensed_tier = None
        active = False

    return {
        "tier": effective_tier,
        "licensed_tier": licensed_tier,
        "status": status,
        "valid": active,
        "features": features,
        "verified_at": verified_at.isoformat() if verified_at else None,
        "offline_grace_until": grace_deadline.isoformat() if grace_deadline else None,
        "entitlement_integrity": integrity_code or ("verified" if active else None),
        "monthly_credits": included_hosted_ai_credits(),
        "hosted_credits_included": included_hosted_ai_credits(),
        "topup_credits": 0,
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


def _validate_server_response(payload: Any, *, machine_id: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise LicenseError(
            "The license server returned an invalid response.",
            code="VERIFY_INVALID_RESPONSE",
            status_code=502,
            retriable=True,
        )
    if payload.get("valid") is not True:
        raise _authoritative_license_error(payload)
    try:
        claims = verify_entitlement_envelope(
            payload.get("entitlement"),
            machine_id=machine_id,
        )
    except EntitlementValidationError as exc:
        raise LicenseError(
            exc.public_message,
            code=exc.code,
            status_code=502,
            retriable=True,
        ) from exc
    return {
        "tier": claims["tier"],
        "claims": claims,
        "entitlement": payload["entitlement"],
        "monthly_credits": included_hosted_ai_credits(),
        "topup_credits": 0,
    }


def _license_verification_endpoints() -> list[str]:
    if (
        bool(getattr(sys, "frozen", False))
        or os.environ.get("GODFIN_PACKAGED") == "1"
    ):
        return list(_PACKAGED_LICENSE_ENDPOINTS)
    endpoints = [
        settings.LICENSE_API_URL.strip(),
        settings.LICENSE_API_FALLBACK_URL.strip(),
    ]
    return list(dict.fromkeys(endpoint for endpoint in endpoints if endpoint))


def verify_with_server(license_key: str) -> dict[str, Any]:
    key = normalize_license_key(license_key)
    if not LICENSE_KEY_PATTERN.fullmatch(key):
        raise LicenseError(
            "Enter a valid GODFIN Pro or Max license key.",
            code="LICENSE_KEY_FORMAT",
            status_code=400,
        )
    machine_id = get_machine_id()
    request_payload = {
        "license_key": key,
        "machine_id": machine_id,
        "device_label": get_device_label(),
        "app_version": settings.VERSION,
    }
    last_error: Exception | None = None
    for endpoint in _license_verification_endpoints():
        try:
            response = httpx.post(
                endpoint,
                json=request_payload,
                headers={"User-Agent": f"GODFIN/{settings.VERSION}"},
                timeout=httpx.Timeout(10.0, connect=5.0),
                follow_redirects=False,
            )
        except httpx.HTTPError as exc:
            last_error = exc
            continue

        try:
            payload = response.json()
        except ValueError as exc:
            last_error = exc
            continue

        if response.status_code >= 500:
            last_error = LicenseError(
                "The license server is unavailable.",
                code="VERIFY_UNAVAILABLE",
                status_code=503,
                retriable=True,
            )
            continue

        # Invalid, revoked, or over-limit licenses are authoritative responses.
        # Never retry them against a second endpoint.
        return _validate_server_response(payload, machine_id=machine_id)

    raise LicenseError(
        "The license server is unavailable. Check your connection and try again.",
        code="VERIFY_UNAVAILABLE",
        status_code=503,
        retriable=True,
    ) from last_error


def activate_license(db: Session, license_key: str) -> dict[str, Any]:
    key = normalize_license_key(license_key)
    verified = verify_with_server(key)
    _set(db, "license_key", encrypt(key))
    _set(
        db,
        "license_entitlement",
        json.dumps(verified["entitlement"], separators=(",", ":"), sort_keys=True),
    )
    _set(db, "license_tier", verified["tier"])
    _set(db, "license_status", "active")
    _set(db, "license_verified_at", str(verified["claims"]["issued_at"]))
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
    try:
        return activate_license(db, key)
    except LicenseError as exc:
        if exc.code in _AUTHORITATIVE_LICENSE_ERRORS:
            _set(db, "license_entitlement", "")
            _set(db, "license_tier", "free")
            _set(
                db,
                "license_status",
                {
                    "LICENSE_SUSPENDED": "suspended",
                    "ACTIVATION_LIMIT": "activation_limit",
                    "DEVICE_LIMIT_REACHED": "activation_limit",
                    "DEVICE_LIMIT": "activation_limit",
                }.get(exc.code, "revoked"),
            )
            _set(db, "license_verified_at", "")
            db.commit()
        raise


def deactivate_license(db: Session) -> dict[str, Any]:
    for key, value in {
        "license_key": "",
        "license_entitlement": "",
        "license_tier": "free",
        "license_status": "inactive",
        "license_verified_at": "",
        "license_monthly_credits": "0",
        "license_topup_credits": "0",
    }.items():
        _set(db, key, value)
    db.commit()
    return license_status(db)
