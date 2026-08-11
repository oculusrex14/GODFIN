"""Verify server-signed, installation-bound license entitlements."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
import uuid
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.core.entitlements import entitlement_manifest, features_for_tier


ENTITLEMENT_SCHEMA_VERSION = 1
ENTITLEMENT_AUDIENCE = "godfin-desktop"
ENTITLEMENT_ISSUER = "godfin-license-service"
MAX_CLOCK_SKEW = timedelta(minutes=5)
MAX_ENTITLEMENT_LIFETIME = timedelta(days=31)
MAX_PAYLOAD_BYTES = 64 * 1024


class EntitlementValidationError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.public_message = message


def _resource_path() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "shared" / "license-entitlement-public-keys.json"
    return (
        Path(__file__).resolve().parents[3]
        / "shared"
        / "license-entitlement-public-keys.json"
    )


def _is_packaged_runtime() -> bool:
    return bool(getattr(sys, "frozen", False)) or os.environ.get(
        "GODFIN_PACKAGED"
    ) == "1"


def _decode_base64url(value: str, *, max_bytes: int) -> bytes:
    if not isinstance(value, str) or not value:
        raise ValueError("missing base64url value")
    if len(value) > ((max_bytes + 2) // 3) * 4:
        raise ValueError("base64url value is too large")
    padding = "=" * (-len(value) % 4)
    decoded = base64.b64decode(
        value + padding,
        altchars=b"-_",
        validate=True,
    )
    if len(decoded) > max_bytes:
        raise ValueError("base64url value is too large")
    return decoded


def _parse_datetime(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise EntitlementValidationError(
            "LICENSE_ENTITLEMENT_INVALID",
            f"The signed license is missing {field}.",
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EntitlementValidationError(
            "LICENSE_ENTITLEMENT_INVALID",
            f"The signed license contains an invalid {field}.",
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def installation_hash(machine_id: str) -> str:
    return hashlib.sha256(
        f"godfin-machine:v1:{machine_id.strip()}".encode("utf-8")
    ).hexdigest()


@lru_cache(maxsize=1)
def public_key_manifest() -> dict[str, Any]:
    override = os.environ.get("GODFIN_LICENSE_PUBLIC_KEYS_JSON", "").strip()
    try:
        if override and not _is_packaged_runtime():
            payload = json.loads(override)
        else:
            payload = json.loads(_resource_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EntitlementValidationError(
            "LICENSE_KEYRING_UNAVAILABLE",
            "The trusted license keyring is unavailable.",
        ) from exc
    if payload.get("schema_version") != 1 or not isinstance(payload.get("keys"), dict):
        raise EntitlementValidationError(
            "LICENSE_KEYRING_INVALID",
            "The trusted license keyring is invalid.",
        )
    return payload


def _public_key(key_version: str) -> Ed25519PublicKey:
    entry = public_key_manifest()["keys"].get(key_version)
    if (
        not isinstance(entry, dict)
        or entry.get("status") not in {"active", "overlap"}
        or entry.get("algorithm") != "Ed25519"
    ):
        raise EntitlementValidationError(
            "LICENSE_SIGNING_KEY_UNKNOWN",
            "The signed license uses an unknown or retired signing key.",
        )
    encoded = entry.get("public_key_spki_b64")
    try:
        key = serialization.load_der_public_key(base64.b64decode(encoded, validate=True))
    except (TypeError, ValueError) as exc:
        raise EntitlementValidationError(
            "LICENSE_KEYRING_INVALID",
            "The trusted license keyring contains an invalid key.",
        ) from exc
    if not isinstance(key, Ed25519PublicKey):
        raise EntitlementValidationError(
            "LICENSE_KEYRING_INVALID",
            "The trusted license keyring contains an unsupported key.",
        )
    return key


def verify_entitlement_envelope(
    envelope: Any,
    *,
    machine_id: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return verified claims or fail closed.

    Payload bytes are verified before their JSON is trusted. Paid features are
    accepted only when the signed feature set exactly matches the bundled
    entitlement manifest for the signed tier.
    """
    if not isinstance(envelope, dict):
        raise EntitlementValidationError(
            "LICENSE_ENTITLEMENT_INVALID",
            "The license server did not return a signed entitlement.",
        )
    if envelope.get("schema_version") != ENTITLEMENT_SCHEMA_VERSION:
        raise EntitlementValidationError(
            "LICENSE_ENTITLEMENT_INVALID",
            "The signed license format is not supported.",
        )
    if envelope.get("algorithm") != "Ed25519":
        raise EntitlementValidationError(
            "LICENSE_ENTITLEMENT_INVALID",
            "The signed license algorithm is not supported.",
        )
    key_version = envelope.get("key_version")
    if not isinstance(key_version, str) or not key_version:
        raise EntitlementValidationError(
            "LICENSE_ENTITLEMENT_INVALID",
            "The signed license is missing its key version.",
        )
    try:
        payload_bytes = _decode_base64url(
            envelope.get("payload"),
            max_bytes=MAX_PAYLOAD_BYTES,
        )
        signature = _decode_base64url(
            envelope.get("signature"),
            max_bytes=64,
        )
        if len(signature) != 64:
            raise ValueError("invalid Ed25519 signature length")
        _public_key(key_version).verify(signature, payload_bytes)
    except EntitlementValidationError:
        raise
    except (InvalidSignature, ValueError, TypeError) as exc:
        raise EntitlementValidationError(
            "LICENSE_SIGNATURE_INVALID",
            "The license server response could not be authenticated.",
        ) from exc

    try:
        claims = json.loads(payload_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EntitlementValidationError(
            "LICENSE_ENTITLEMENT_INVALID",
            "The signed license payload is invalid.",
        ) from exc
    if not isinstance(claims, dict):
        raise EntitlementValidationError(
            "LICENSE_ENTITLEMENT_INVALID",
            "The signed license payload is invalid.",
        )

    if (
        claims.get("schema_version") != ENTITLEMENT_SCHEMA_VERSION
        or claims.get("audience") != ENTITLEMENT_AUDIENCE
        or claims.get("issuer") != ENTITLEMENT_ISSUER
        or claims.get("key_version") != key_version
    ):
        raise EntitlementValidationError(
            "LICENSE_ENTITLEMENT_INVALID",
            "The signed license claims are not valid for this app.",
        )

    tier = claims.get("tier")
    features = claims.get("features")
    if tier not in {"pro", "max"} or not isinstance(features, list):
        raise EntitlementValidationError(
            "LICENSE_ENTITLEMENT_INVALID",
            "The signed license contains an unknown plan.",
        )
    expected_features = features_for_tier(tier)
    if features != expected_features:
        raise EntitlementValidationError(
            "LICENSE_ENTITLEMENT_INVALID",
            "The signed license features do not match this app version.",
        )
    if claims.get("entitlement_version") != entitlement_manifest().get("schema_version"):
        raise EntitlementValidationError(
            "LICENSE_ENTITLEMENT_INVALID",
            "The signed license entitlement version is not supported.",
        )
    if claims.get("installation_hash") != installation_hash(machine_id):
        raise EntitlementValidationError(
            "LICENSE_MACHINE_MISMATCH",
            "This signed license belongs to a different installation.",
        )

    try:
        uuid.UUID(str(claims.get("license_id")))
        uuid.UUID(str(claims.get("token_id")))
    except (TypeError, ValueError, AttributeError) as exc:
        raise EntitlementValidationError(
            "LICENSE_ENTITLEMENT_INVALID",
            "The signed license identifiers are invalid.",
        ) from exc
    state_version = claims.get("license_state_version")
    if (
        not isinstance(state_version, int)
        or isinstance(state_version, bool)
        or state_version < 1
    ):
        raise EntitlementValidationError(
            "LICENSE_ENTITLEMENT_INVALID",
            "The signed license state version is invalid.",
        )

    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    now = now.astimezone(UTC)
    issued_at = _parse_datetime(claims.get("issued_at"), "issued_at")
    expires_at = _parse_datetime(claims.get("expires_at"), "expires_at")
    if issued_at > now + MAX_CLOCK_SKEW:
        raise EntitlementValidationError(
            "LICENSE_ENTITLEMENT_FUTURE",
            "The signed license was issued in the future.",
        )
    if expires_at <= issued_at or expires_at - issued_at > MAX_ENTITLEMENT_LIFETIME:
        raise EntitlementValidationError(
            "LICENSE_ENTITLEMENT_INVALID",
            "The signed license lifetime is invalid.",
        )
    if now > expires_at:
        raise EntitlementValidationError(
            "LICENSE_ENTITLEMENT_EXPIRED",
            "Reconnect to renew this signed license.",
        )
    return claims
