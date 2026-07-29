from __future__ import annotations

import json
import os
from datetime import datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.feature_flags import feature_enabled
from app.core.reward_pilot import PAYOUT_POLICY, build_redacted_preview
from app.models.app_setting import AppSetting
from app.models.reward_pilot import RewardPilotSubmission

router = APIRouter()
CONSENT_KEY = "reward_pilot_consent"
CONSENT_VERSION_KEY = "reward_pilot_consent_version"
CONSENT_VERSION = "2026-07-29.v1"


class ConsentUpdate(BaseModel):
    consented: bool


def _consented(db: Session) -> bool:
    setting = db.query(AppSetting).filter_by(key=CONSENT_KEY).first()
    version = db.query(AppSetting).filter_by(key=CONSENT_VERSION_KEY).first()
    return bool(
        setting
        and setting.value == "true"
        and version
        and version.value == CONSENT_VERSION
    )


def _set(db: Session, key: str, value: str) -> None:
    setting = db.query(AppSetting).filter_by(key=key).first()
    if setting:
        setting.value = value
    else:
        db.add(AppSetting(key=key, value=value))


@router.get("/status")
def status(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    return {
        "enabled": feature_enabled(db, "reward_pilot"),
        "consented": _consented(db),
        "consent_version": CONSENT_VERSION,
        "off_by_default": True,
        "payout_policy": PAYOUT_POLICY,
        "privacy": (
            "Only a reviewed coarse aggregate may be submitted. Payout identity "
            "is collected separately from pseudonymized contributions."
        ),
    }


@router.put("/consent")
def update_consent(
    body: ConsentUpdate,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    _set(db, CONSENT_KEY, "true" if body.consented else "false")
    _set(db, CONSENT_VERSION_KEY, CONSENT_VERSION if body.consented else "")
    db.commit()
    return status(db, True)


@router.get("/preview")
def preview(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    if not feature_enabled(db, "reward_pilot"):
        raise HTTPException(status_code=404, detail="The compensated-data pilot is closed.")
    if not _consented(db):
        raise HTTPException(
            status_code=409, detail="Separate pilot consent is required first."
        )
    return build_redacted_preview(db)


@router.post("/submit")
def submit(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    if not feature_enabled(db, "reward_pilot"):
        raise HTTPException(status_code=404, detail="The compensated-data pilot is closed.")
    if not _consented(db):
        raise HTTPException(
            status_code=409, detail="Separate pilot consent is required first."
        )
    preview_payload = build_redacted_preview(db)
    if not preview_payload["eligible"]:
        raise HTTPException(
            status_code=409,
            detail="An accepted aggregate bundle requires a complete 90-day window.",
        )
    submission_url = os.environ.get("GODFIN_REWARD_PILOT_URL", "").strip()
    if not submission_url:
        raise HTTPException(
            status_code=503,
            detail="Pilot submission is not configured in this private build.",
        )
    if not submission_url.startswith("https://"):
        raise HTTPException(
            status_code=503,
            detail="Pilot submission requires an HTTPS endpoint.",
        )
    existing = (
        db.query(RewardPilotSubmission)
        .filter_by(payload_digest=preview_payload["digest"])
        .first()
    )
    if existing and existing.status == "submitted":
        return {
            "status": existing.status,
            "receipt_id": existing.receipt_id,
            "digest": existing.payload_digest,
        }
    submission = existing or RewardPilotSubmission(
        payload_json=json.dumps(preview_payload["payload"], sort_keys=True),
        payload_digest=preview_payload["digest"],
    )
    if not existing:
        db.add(submission)
        db.commit()
    try:
        response = httpx.post(
            submission_url,
            json={
                "digest": submission.payload_digest,
                "payload": preview_payload["payload"],
                "consent_version": CONSENT_VERSION,
            },
            timeout=httpx.Timeout(10.0, connect=5.0),
            follow_redirects=False,
        )
        response.raise_for_status()
        result = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        submission.status = "failed"
        db.commit()
        raise HTTPException(
            status_code=502, detail="The pilot service did not accept the bundle."
        ) from exc
    submission.status = "submitted"
    submission.receipt_id = str(result.get("receipt_id") or "")[:120] or None
    submission.submitted_at = datetime.utcnow()
    db.commit()
    return {
        "status": submission.status,
        "receipt_id": submission.receipt_id,
        "digest": submission.payload_digest,
    }
