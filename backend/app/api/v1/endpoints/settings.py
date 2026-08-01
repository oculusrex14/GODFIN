from __future__ import annotations

import os
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.backup import create_backup, list_backups
from app.core.config import settings as app_config
from app.core.database import get_db
from app.core.encryption import SecretDecryptionError, decrypt, get_encryption_health
from app.core.license import license_status
from app.core.pin_security import client_ip_from_request, require_current_pin
from app.models.app_setting import AppSetting
from app.models.classification_rule import ClassificationRule
from app.models.llm_config import LLMConfiguration

router = APIRouter()

DB_PATH = str(app_config.database_path)
PUBLIC_SETTING_KEYS = frozenset(
    {
        "allow_network_access",
        "auto_ingestion_enabled",
        "backup_directory",
        "developer_mode",
        "enable_embeddings",
        "ingestion_frequency_minutes",
        "local_ai_choice",
        "user_timezone",
    }
)


def _get_backup_dir(db: Session) -> str:
    setting = db.query(AppSetting).filter_by(key='backup_directory').first()
    return setting.value if setting else './backups'


# --- App Settings ---

@router.get("")
def get_settings(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    settings = db.query(AppSetting).all()
    return {s.key: s.value for s in settings if s.key in PUBLIC_SETTING_KEYS}


class TimezoneUpdate(BaseModel):
    timezone: str = Field(..., min_length=1, max_length=64)


class SensitiveToggleUpdate(BaseModel):
    enabled: bool
    current_pin: str | None = Field(
        default=None,
        min_length=4,
        max_length=8,
        pattern=r"^\d+$",
    )


def _set_existing_setting(db: Session, key: str, value: str) -> None:
    setting = db.query(AppSetting).filter_by(key=key).first()
    if setting is None:
        raise HTTPException(status_code=500, detail="Required application setting is missing")
    setting.value = value


@router.get("/health")
def settings_health(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    from app.core.gmail_service import CLIENT_SECRETS_FILE, TOKEN_FILE, gmail_service

    encryption = get_encryption_health()

    gmail_connected = gmail_service.is_connected
    if gmail_connected:
        gmail_status = "connected"
        gmail_message = "Gmail credentials are valid."
    elif TOKEN_FILE.exists():
        gmail_status = "needs_reauth"
        gmail_message = "Stored Gmail credentials need to be re-authorized."
    elif CLIENT_SECRETS_FILE.exists() or (
        os.environ.get("GOOGLE_CLIENT_ID") and os.environ.get("GOOGLE_CLIENT_SECRET")
    ):
        gmail_status = "ready"
        gmail_message = "Gmail is configured and ready to connect."
    else:
        gmail_status = "not_configured"
        gmail_message = "Add Google OAuth credentials to connect Gmail."

    active_llm = db.query(LLMConfiguration).filter_by(is_active=True).first()
    llm_status = "not_configured"
    llm_message = "No LLM provider is active. Rules-only classification is available."
    if active_llm:
        llm_status = "ok"
        llm_message = f"{active_llm.provider} / {active_llm.model} is active."
        from app.core.llm_privacy import has_hosted_data_consent

        if not has_hosted_data_consent(active_llm):
            llm_status = "consent_required"
            llm_message = "Review the hosted AI data disclosure before using this provider."
        if active_llm.api_key:
            try:
                decrypt(active_llm.api_key)
            except SecretDecryptionError:
                llm_status = "decrypt_failed"
                llm_message = "Re-enter the API key for the active LLM provider."

    backup_dir = _get_backup_dir(db)
    backups = list_backups(backup_dir)
    latest_backup = backups[0] if backups else None

    last_ingest = db.query(AppSetting).filter_by(key="last_ingestion_run").first()
    network_setting = db.query(AppSetting).filter_by(key="allow_network_access").first()
    license_health = license_status(db)

    return {
        "encryption": encryption,
        "gmail": {
            "status": gmail_status,
            "connected": gmail_connected,
            "message": gmail_message,
        },
        "llm": {
            "status": llm_status,
            "provider": active_llm.provider if active_llm else None,
            "model": active_llm.model if active_llm else None,
            "message": llm_message,
        },
        "backup": {
            "status": "ok" if latest_backup else "never",
            "directory": backup_dir,
            "count": len(backups),
            "last_backup": latest_backup,
            "message": (
                "Backups are available."
                if latest_backup
                else "No backup has been created yet."
            ),
        },
        "ingestion": {
            "status": "ok" if last_ingest and last_ingest.value else "never",
            "last_run": last_ingest.value if last_ingest else None,
        },
        "network": {
            "allow_network_access": bool(
                network_setting and network_setting.value == "true"
            ),
            "message": "A restart is required after changing network access.",
        },
        "license": {
            "status": "ok" if license_health["valid"] else license_health["status"],
            "tier": license_health["tier"],
            "message": license_health["message"],
        },
    }


@router.put("/preferences/timezone")
def update_timezone(
    body: TimezoneUpdate,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    try:
        ZoneInfo(body.timezone)
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(status_code=422, detail="Unknown IANA timezone") from exc

    _set_existing_setting(db, "user_timezone", body.timezone)
    db.commit()
    return {"key": "user_timezone", "value": body.timezone, "restart_required": False}


@router.put("/preferences/network-access")
def update_network_access(
    body: SensitiveToggleUpdate,
    request: Request,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    if body.enabled:
        require_current_pin(
            db,
            body.current_pin,
            client_ip_from_request(request),
            missing_detail="Enter your current PIN to make this security change",
        )
    value = "true" if body.enabled else "false"
    _set_existing_setting(db, "allow_network_access", value)
    db.commit()
    return {
        "key": "allow_network_access",
        "value": value,
        "restart_required": True,
    }


@router.put("/preferences/developer-mode")
def update_developer_mode(
    body: SensitiveToggleUpdate,
    request: Request,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    if body.enabled:
        require_current_pin(
            db,
            body.current_pin,
            client_ip_from_request(request),
            missing_detail="Enter your current PIN to make this security change",
        )
    value = "true" if body.enabled else "false"
    _set_existing_setting(db, "developer_mode", value)
    db.commit()
    return {"key": "developer_mode", "value": value, "restart_required": False}


@router.put("/{key}", include_in_schema=False)
def reject_generic_setting_mutation(
    key: str,
    _body: dict,
    _user: bool = Depends(get_current_user),
):
    del key
    raise HTTPException(
        status_code=403,
        detail="This setting cannot be changed through the generic settings API",
    )


# --- Backup ---

@router.post("/backup")
def trigger_backup(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    backup_dir = _get_backup_dir(db)
    try:
        filename = create_backup(DB_PATH, backup_dir)
        return {'filename': filename, 'status': 'success'}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/backups")
def get_backups(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    backup_dir = _get_backup_dir(db)
    return list_backups(backup_dir)


# --- Developer Mode ---

@router.get("/developer")
def developer_mode_status(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    from sqlalchemy import func
    from app.models.transaction import Transaction
    from app.models.merchant_memory import MerchantMemory

    setting = db.query(AppSetting).filter_by(key='developer_mode').first()
    enabled = setting.value == 'true' if setting else False

    rules = db.query(ClassificationRule).filter_by(is_active=True).all()
    rules_list = [
        {
            'id': r.id,
            'rule_type': r.rule_type,
            'pattern': r.pattern,
            'category': r.category,
            'subcategory': r.subcategory,
            'priority': r.priority,
            'is_system': r.is_system,
        }
        for r in rules
    ]

    # Classification health metrics
    source_breakdown = (
        db.query(Transaction.classification_source, func.count(Transaction.id))
        .filter(Transaction.status != 'deleted', Transaction.classification_source.isnot(None))
        .group_by(Transaction.classification_source)
        .all()
    )
    source_counts = {source: count for source, count in source_breakdown}

    avg_confidence_rows = (
        db.query(Transaction.classification_source, func.avg(Transaction.confidence))
        .filter(Transaction.status != 'deleted', Transaction.confidence.isnot(None))
        .group_by(Transaction.classification_source)
        .all()
    )
    avg_confidence = {source: round(float(avg), 3) for source, avg in avg_confidence_rows if avg is not None}

    unclassified = (
        db.query(func.count(Transaction.id))
        .filter(Transaction.status != 'deleted', Transaction.category.is_(None))
        .scalar()
    )

    merchant_memory_count = db.query(func.count(MerchantMemory.id)).scalar()

    return {
        'developer_mode': enabled,
        'rules': rules_list,
        'classification_health': {
            'source_counts': source_counts,
            'avg_confidence': avg_confidence,
            'unclassified_count': unclassified or 0,
            'merchant_memory_count': merchant_memory_count or 0,
            'active_rules_count': len(rules_list),
        },
    }


class RuleCreate(BaseModel):
    rule_type: str = Field(..., pattern=r'^(regex|contains|exact)$')
    pattern: str = Field(..., min_length=1)
    category: str = Field(..., min_length=1)
    subcategory: str = None
    priority: int = 100


class RuleUpdate(BaseModel):
    pattern: str = Field(None, min_length=1)
    category: str = Field(None, min_length=1)
    subcategory: str = None
    priority: int = None


@router.post("/developer/rules", status_code=201)
def create_rule(
    body: RuleCreate,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    setting = db.query(AppSetting).filter_by(key='developer_mode').first()
    if not setting or setting.value != 'true':
        raise HTTPException(status_code=403, detail="Developer mode is not enabled")

    if body.rule_type == 'regex':
        try:
            re.compile(body.pattern)
        except re.error as e:
            raise HTTPException(status_code=400, detail=f"Invalid regex: {e}")

    import uuid
    rule = ClassificationRule(
        id=str(uuid.uuid4()),
        rule_type=body.rule_type,
        pattern=body.pattern,
        category=body.category,
        subcategory=body.subcategory,
        priority=body.priority,
        is_system=False,
        is_active=True,
    )
    db.add(rule)
    db.commit()
    return {
        'id': rule.id,
        'rule_type': rule.rule_type,
        'pattern': rule.pattern,
        'category': rule.category,
        'subcategory': rule.subcategory,
        'priority': rule.priority,
        'is_system': False,
    }


@router.put("/developer/rules/{rule_id}")
def update_rule(
    rule_id: str,
    body: RuleUpdate,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    # Check developer mode is enabled
    setting = db.query(AppSetting).filter_by(key='developer_mode').first()
    if not setting or setting.value != 'true':
        raise HTTPException(status_code=403, detail="Developer mode is not enabled")

    rule = db.query(ClassificationRule).filter_by(id=rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    if body.pattern is not None:
        # Validate regex if rule_type is regex
        if rule.rule_type == 'regex':
            try:
                re.compile(body.pattern)
            except re.error as e:
                raise HTTPException(status_code=400, detail=f"Invalid regex: {e}")
        rule.pattern = body.pattern

    if body.category is not None:
        rule.category = body.category
    if body.subcategory is not None:
        rule.subcategory = body.subcategory
    if body.priority is not None:
        rule.priority = body.priority

    db.commit()
    return {'id': rule.id, 'status': 'updated'}


@router.delete("/developer/rules/{rule_id}", status_code=204)
def delete_rule(
    rule_id: str,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    setting = db.query(AppSetting).filter_by(key='developer_mode').first()
    if not setting or setting.value != 'true':
        raise HTTPException(status_code=403, detail="Developer mode is not enabled")

    rule = db.query(ClassificationRule).filter_by(id=rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    db.delete(rule)
    db.commit()


# --- Reset Data ---

class ResetDataRequest(BaseModel):
    pin: str = Field(..., min_length=1)
    create_backup: bool = True


class ClassificationMemoryReset(BaseModel):
    pin: str = Field(..., min_length=4, max_length=8)


class PersonalClassifierUpdate(BaseModel):
    enabled: bool


@router.get("/classification-memory")
def classification_memory(
    limit: int = 100,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    from app.core.classification_learning import list_learning_memory

    return list_learning_memory(db, limit=min(max(limit, 1), 500))


@router.get("/classification-memory/export")
def export_classification_memory(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    from app.core.classification_learning import export_learning_memory_csv

    return Response(
        content=export_learning_memory_csv(db),
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=godfin-classification-memory.csv"
        },
    )


@router.post("/classification-memory/{correction_id}/undo")
def undo_classification_memory(
    correction_id: str,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    from app.core.classification_learning import undo_correction

    try:
        correction = undo_correction(db, correction_id)
        db.commit()
        return {
            "status": "undone",
            "correction_id": correction.id,
            "transaction_id": correction.transaction_id,
        }
    except ValueError as exc:
        db.rollback()
        message = str(exc)
        status_code = 409 if "Finalized" in message or "already" in message else 404
        raise HTTPException(status_code=status_code, detail=message) from exc


@router.put("/classification-memory/personal")
def update_personal_classifier(
    body: PersonalClassifierUpdate,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    from app.core.classification_learning import personal_classifier_eligibility

    eligibility = personal_classifier_eligibility(db)
    if body.enabled and "personal_classifier" not in license_status(db)["features"]:
        raise HTTPException(
            status_code=403,
            detail="The personal classifier is a GODFIN Max feature.",
        )
    if body.enabled and not eligibility["eligible"]:
        raise HTTPException(
            status_code=409,
            detail=(
                "Personal classification requires at least "
                f"{eligibility['required_corrections']} confirmed corrections "
                f"across {eligibility['required_categories']} categories."
            ),
        )
    setting = db.query(AppSetting).filter_by(
        key="personal_classification_enabled"
    ).first()
    if setting is None:
        setting = AppSetting(
            key="personal_classification_enabled",
            value="true" if body.enabled else "false",
        )
        db.add(setting)
    else:
        setting.value = "true" if body.enabled else "false"
    db.commit()
    return personal_classifier_eligibility(db)


@router.post("/classification-memory/reset")
def reset_classification_memory(
    body: ClassificationMemoryReset,
    request: Request,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    from app.core.classification_learning import reset_learning_memory

    require_current_pin(db, body.pin, client_ip_from_request(request))
    backup_filename = create_backup(DB_PATH, _get_backup_dir(db))
    result = reset_learning_memory(db)
    db.commit()
    return {
        **result,
        "backup_filename": backup_filename,
        "message": "Classification memory reset. Existing transaction labels were preserved.",
    }


@router.post("/reset-data", status_code=200)
def reset_all_data(
    body: ResetDataRequest,
    request: Request,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Reset all transaction and dynamic data. PIN-protected."""
    # 1. Verify PIN
    require_current_pin(db, body.pin, client_ip_from_request(request))

    # 2. Create backup first (safety net)
    backup_filename = None
    if body.create_backup:
        try:
            backup_dir = _get_backup_dir(db)
            backup_filename = create_backup(DB_PATH, backup_dir)
        except Exception:
            pass  # Don't fail the reset if backup fails

    # 3. Delete all dynamic data (preserve accounts, settings, rules)
    from app.models.transaction import Transaction
    from app.models.transaction_split import TransactionSplit
    from app.models.audit_session import AuditSession
    from app.models.audit_log import AuditLog
    from app.models.merchant_memory import MerchantMemory
    from app.models.monthly_aggregate import MonthlyAggregate
    from app.models.recurring_pattern import RecurringPattern
    from app.models.goal import Goal
    from app.models.income_source import IncomeSource
    from app.models.subscription import Subscription
    from app.models.system_log import SystemLog
    from app.models.classification_learning import (
        ClassificationCorrection,
        ClassificationPattern,
    )
    from app.models.behavior_insight import BehaviorInsightPreference
    from app.models.net_worth import NetWorthItem, NetWorthQuote
    from app.models.reward_pilot import RewardPilotSubmission

    # Delete child tables FIRST (FK order matters):
    # TransactionSplit → Transaction; AuditLog → Transaction
    # Transaction → AuditSession; MonthlyAggregate → AuditSession
    db.query(TransactionSplit).delete(synchronize_session=False)
    db.query(AuditLog).delete(synchronize_session=False)
    db.query(NetWorthQuote).delete(synchronize_session=False)
    db.query(NetWorthItem).delete(synchronize_session=False)
    db.query(BehaviorInsightPreference).delete(synchronize_session=False)
    db.query(RewardPilotSubmission).delete(synchronize_session=False)
    db.query(ClassificationCorrection).delete(synchronize_session=False)
    db.query(ClassificationPattern).delete(synchronize_session=False)
    db.query(Transaction).delete(synchronize_session=False)
    db.query(MonthlyAggregate).delete(synchronize_session=False)
    db.query(AuditSession).delete(synchronize_session=False)
    db.query(MerchantMemory).delete(synchronize_session=False)
    db.query(RecurringPattern).delete(synchronize_session=False)
    db.query(Goal).delete(synchronize_session=False)
    db.query(IncomeSource).delete(synchronize_session=False)
    db.query(Subscription).delete(synchronize_session=False)
    db.query(SystemLog).delete(synchronize_session=False)

    # 4. Reset ingestion tracking state
    for key in ['last_ingestion_run', 'last_gmail_history_id', 'ingestion_history']:
        setting = db.query(AppSetting).filter_by(key=key).first()
        if setting:
            setting.value = ''

    db.commit()

    return {
        'success': True,
        'backup_created': backup_filename is not None,
        'backup_filename': backup_filename,
        'message': 'All data has been reset. Accounts and settings preserved.',
    }
