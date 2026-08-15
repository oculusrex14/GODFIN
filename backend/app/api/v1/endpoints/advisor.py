"""Financial Advisor AI chat endpoint."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.v1.entitlements import require_entitlement
from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.errors import IntegrationUnavailableError, StateConflictError
from app.core.advisor_service import chat
from app.core.advisor_digest import build_weekly_digest, digest_to_html
from app.core.gmail_service import gmail_service
from app.models.app_setting import AppSetting
from app.schemas.financial import ChatRole

router = APIRouter()
AI_CLASSIFICATION_ENTITLEMENT = require_entitlement("ai_classification")
ADVANCED_REPORTS_ENTITLEMENT = require_entitlement("advanced_reports")


class ChatMessage(BaseModel):
    role: ChatRole
    content: str = Field(min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    history: List[ChatMessage] = Field(default_factory=list, max_length=20)


class ChatResponse(BaseModel):
    reply: str


class DigestSettingsUpdate(BaseModel):
    enabled: bool
    recipient: str | None = Field(default=None, max_length=254)


class DigestPeriodResponse(BaseModel):
    start: str
    end: str


class DigestAnomalyResponse(BaseModel):
    transaction_id: str
    merchant: str
    amount: float
    date: str
    reason: str


class DigestBudgetBreachResponse(BaseModel):
    goal_id: str
    name: str
    current_saved: float
    expected_saved: float
    shortfall: float


class DigestMerchantResponse(BaseModel):
    name: str
    category: str
    first_seen: str


class WeeklyDigestResponse(BaseModel):
    period: DigestPeriodResponse
    generated_at: str
    current_spend: float
    previous_spend: float
    spending_velocity_percent: float | None
    spending_velocity_message: str
    anomalies: list[DigestAnomalyResponse]
    budget_breaches: list[DigestBudgetBreachResponse]
    new_merchants: list[DigestMerchantResponse]


class DigestSettingsResponse(BaseModel):
    enabled: bool
    recipient: str | None
    last_sent: str | None
    gmail_connected: bool
    gmail_send_supported: bool


class DigestSendResponse(BaseModel):
    sent: bool
    recipient: str


@router.post(
    "/chat",
    response_model=ChatResponse,
    dependencies=[Depends(AI_CLASSIFICATION_ENTITLEMENT)],
)
def advisor_chat(
    body: ChatRequest,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Send a message to the financial advisor AI."""
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


def _setting_value(db: Session, key: str, default: str = "") -> str:
    setting = db.query(AppSetting).filter_by(key=key).first()
    return setting.value if setting is not None else default


@router.get(
    "/digest",
    dependencies=[Depends(ADVANCED_REPORTS_ENTITLEMENT)],
    response_model=WeeklyDigestResponse,
)
def advisor_weekly_digest(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    return build_weekly_digest(db)


@router.get("/digest/settings", response_model=DigestSettingsResponse)
def get_digest_settings(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    enabled = _setting_value(db, "advisor_weekly_digest_enabled", "false")
    recipient = _setting_value(db, "advisor_weekly_digest_recipient", "")
    last_sent = _setting_value(db, "advisor_weekly_digest_last_sent", "")
    return {
        "enabled": enabled == "true",
        "recipient": recipient or None,
        "last_sent": last_sent or None,
        "gmail_connected": gmail_service.is_connected,
        "gmail_send_supported": gmail_service.can_send,
    }


@router.put(
    "/digest/settings",
    dependencies=[Depends(ADVANCED_REPORTS_ENTITLEMENT)],
    response_model=DigestSettingsResponse,
)
def update_digest_settings(
    body: DigestSettingsUpdate,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
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


@router.post(
    "/digest/send",
    dependencies=[Depends(ADVANCED_REPORTS_ENTITLEMENT)],
    response_model=DigestSendResponse,
)
def send_advisor_digest(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    recipient = _setting_value(db, "advisor_weekly_digest_recipient", "")
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
        raise StateConflictError(
            code="GMAIL_SEND_NOT_READY",
            message="Gmail is not ready to send the weekly digest.",
            hint="Reconnect Gmail in Settings, then try again.",
        ) from error
    except Exception as error:
        raise IntegrationUnavailableError(
            code="GMAIL_SEND_FAILED",
            message="Gmail could not send the weekly digest.",
            hint="Check your connection and Gmail status, then try again.",
        ) from error
    from datetime import datetime

    _get_setting(db, "advisor_weekly_digest_last_sent", "").value = (
        datetime.now().isoformat()
    )
    db.commit()
    return {"sent": True, "recipient": recipient}
