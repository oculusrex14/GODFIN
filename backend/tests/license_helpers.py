from __future__ import annotations

import base64
import json
import uuid
from datetime import UTC, datetime, timedelta

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy.orm import Session

from app.core.entitlements import entitlement_manifest, features_for_tier
from app.core.license import get_machine_id
from app.core.license_entitlement import installation_hash
from app.models.app_setting import AppSetting


TEST_KEY_VERSION = "test-ed25519-v1"
TEST_SIGNER = Ed25519PrivateKey.from_private_bytes(bytes(range(1, 33)))


def test_public_key_manifest_json() -> str:
    public_der = TEST_SIGNER.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return json.dumps(
        {
            "schema_version": 1,
            "keys": {
                TEST_KEY_VERSION: {
                    "status": "active",
                    "algorithm": "Ed25519",
                    "public_key_spki_b64": base64.b64encode(public_der).decode(),
                }
            },
        },
        separators=(",", ":"),
        sort_keys=True,
    )


def signed_entitlement(
    tier: str = "pro",
    *,
    machine_id: str | None = None,
    issued_at: datetime | None = None,
    expires_at: datetime | None = None,
    key_version: str = TEST_KEY_VERSION,
    signer: Ed25519PrivateKey = TEST_SIGNER,
    license_id: str | None = None,
    state_version: int = 1,
    claim_overrides: dict[str, object] | None = None,
) -> dict[str, object]:
    issued_at = (issued_at or datetime.now(UTC)).astimezone(UTC)
    expires_at = (expires_at or issued_at + timedelta(days=7)).astimezone(UTC)
    claims = {
        "schema_version": 1,
        "issuer": "godfin-license-service",
        "audience": "godfin-desktop",
        "key_version": key_version,
        "license_id": license_id or str(uuid.uuid4()),
        "tier": tier,
        "features": features_for_tier(tier),
        "entitlement_version": entitlement_manifest()["schema_version"],
        "installation_hash": installation_hash(machine_id or get_machine_id()),
        "issued_at": issued_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "token_id": str(uuid.uuid4()),
        "license_state_version": state_version,
    }
    claims.update(claim_overrides or {})
    payload = json.dumps(claims, separators=(",", ":"), sort_keys=True).encode()
    return {
        "schema_version": 1,
        "algorithm": "Ed25519",
        "key_version": key_version,
        "payload": base64.urlsafe_b64encode(payload).decode().rstrip("="),
        "signature": base64.urlsafe_b64encode(signer.sign(payload))
        .decode()
        .rstrip("="),
    }


def signed_server_response(
    tier: str = "pro",
    *,
    machine_id: str | None = None,
    issued_at: datetime | None = None,
    expires_at: datetime | None = None,
) -> dict[str, object]:
    return {
        "valid": True,
        "tier": tier,
        "entitlement": signed_entitlement(
            tier,
            machine_id=machine_id,
            issued_at=issued_at,
            expires_at=expires_at,
        ),
    }


def install_test_license(
    db: Session,
    tier: str = "pro",
    *,
    issued_at: datetime | None = None,
    expires_at: datetime | None = None,
) -> None:
    envelope = signed_entitlement(
        tier,
        issued_at=issued_at,
        expires_at=expires_at,
    )
    values = {
        "license_entitlement": json.dumps(
            envelope,
            separators=(",", ":"),
            sort_keys=True,
        ),
        "license_tier": tier,
        "license_status": "active",
        "license_verified_at": (issued_at or datetime.now(UTC)).isoformat(),
    }
    for key, value in values.items():
        setting = db.query(AppSetting).filter_by(key=key).first()
        if setting is None:
            db.add(AppSetting(key=key, value=value))
        else:
            setting.value = value
    db.commit()
