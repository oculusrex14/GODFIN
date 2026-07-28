"""Financial Advisor AI chat endpoint."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.advisor_service import chat
from app.core.advisor_digest import build_weekly_digest, digest_to_html
from app.api.v1.endpoints.license import enforce_feature
from app.core.gmail_service import gmail_service
from app.models.app_setting import AppSetting

router = APIRouter()


class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    history: List[ChatMessage] = []


class ChatResponse(BaseModel):
    reply: str


class DigestSettingsUpdate(BaseModel):
    enabled: bool
    recipient: str | None = None


@router.post("/chat", response_model=ChatResponse)
def advisor_chat(
    body: ChatRequest,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Send a message to the financial advisor AI."""
    enforce_feature(db, "ai_classification")
    if not body.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    history = [{"role": m.role, "content": m.content} for m in body.history]

    reply = chat(db, body.message.strip(), history)
    if reply is None:
        raise HTTPException(
            status_code=503,
            detail="AI advisor is unavailable. Please configure an LLM provider in Settings."
        )

    return ChatResponse(reply=reply)


def _get_setting(db: Session, key: str, default: str = "") -> AppSetting:
    setting = db.query(AppSetting).filter_by(key=key).first()
    if setting is None:
        setting = AppSetting(key=key, value=default)
        db.add(setting)
        db.flush()
    return setting


@router.get("/digest")
def advisor_weekly_digest(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    enforce_feature(db, "advanced_reports")
    return build_weekly_digest(db)


@router.get("/digest/settings")
def get_digest_settings(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    enabled = _get_setting(db, "advisor_weekly_digest_enabled", "false")
    recipient = _get_setting(db, "advisor_weekly_digest_recipient", "")
    last_sent = _get_setting(db, "advisor_weekly_digest_last_sent", "")
    db.commit()
    return {
        "enabled": enabled.value == "true",
        "recipient": recipient.value or None,
        "last_sent": last_sent.value or None,
        "gmail_connected": gmail_service.is_connected,
        "gmail_send_supported": gmail_service.can_send,
    }


@router.put("/digest/settings")
def update_digest_settings(
    body: DigestSettingsUpdate,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    enforce_feature(db, "advanced_reports")
    recipient = (body.recipient or "").strip()
    if body.enabled and "@" not in recipient:
        raise HTTPException(
            status_code=400,
            detail="A valid recipient email is required to enable the digest.",
        )
    _get_setting(db, "advisor_weekly_digest_enabled", "false").value = (
        "true" if body.enabled else "false"
    )
    _get_setting(db, "advisor_weekly_digest_recipient", "").value = recipient
    db.commit()
    return get_digest_settings(db, _user=True)


@router.post("/digest/send")
def send_advisor_digest(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    enforce_feature(db, "advanced_reports")
    recipient = _get_setting(db, "advisor_weekly_digest_recipient", "").value
    if not recipient:
        raise HTTPException(status_code=400, detail="Configure a digest recipient first.")
    digest = build_weekly_digest(db)
    try:
        gmail_service.send_email(
            recipient,
            f"GODFIN weekly digest · {digest['period']['end']}",
            digest_to_html(digest),
        )
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(
            status_code=502, detail="Gmail could not send the weekly digest."
        ) from error
    from datetime import datetime

    _get_setting(db, "advisor_weekly_digest_last_sent", "").value = (
        datetime.now().isoformat()
    )
    db.commit()
    return {"sent": True, "recipient": recipient}
