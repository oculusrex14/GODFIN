from __future__ import annotations

import logging
import os
import re
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.backup import create_backup, list_backups
from app.core.config import settings as app_config
from app.core.data_deletion import reset_dynamic_data
from app.core.database import get_db
from app.core.errors import LocalOperationError
from app.core.encryption import SecretDecryptionError, decrypt, get_encryption_health
from app.core.license import license_status
from app.core.pin_security import client_ip_from_request, require_current_pin
from app.core.restore_request import (
    default_restore_request_path,
    prepare_restore_request,
)
from app.core.startup_migrations import CURRENT_SCHEMA_REVISION
from app.models.app_setting import AppSetting
from app.models.classification_rule import ClassificationRule
from app.models.classification_learning import ClassificationCorrection
from app.models.llm_config import LLMConfiguration

logger = logging.getLogger(__name__)
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


def _safe_nonnegative_int(value: str | None) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


# --- App Settings ---

@router.get("", response_model=dict[str, str])
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


class PreferenceUpdateResponse(BaseModel):
    key: str
    value: str
    restart_required: bool


class EncryptionHealthResponse(BaseModel):
    status: str
    source: str | None
    message: str


class GmailHealthResponse(BaseModel):
    status: str
    connected: bool
    message: str
    retryable: bool
    action_required: str | None


class LLMHealthResponse(BaseModel):
    status: str
    provider: str | None
    model: str | None
    message: str


class BackupFileResponse(BaseModel):
    filename: str
    size_bytes: int
    created_at: str
    restore_ready: bool


class BackupHealthResponse(BaseModel):
    status: str
    scheduler_status: str
    job_status: str
    directory: str
    count: int
    last_backup: BackupFileResponse | None
    last_success_at: str | None
    last_failure_at: str | None
    next_retry_at: str | None
    failure_code: str | None
    failure_count: int
    message: str


class IngestionHealthResponse(BaseModel):
    status: str
    last_run: str | None


class NetworkHealthResponse(BaseModel):
    allow_network_access: bool
    message: str


class LicenseHealthResponse(BaseModel):
    status: str
    tier: str
    message: str


class SettingsHealthResponse(BaseModel):
    encryption: EncryptionHealthResponse
    gmail: GmailHealthResponse
    llm: LLMHealthResponse
    backup: BackupHealthResponse
    ingestion: IngestionHealthResponse
    network: NetworkHealthResponse
    license: LicenseHealthResponse


def _set_existing_setting(db: Session, key: str, value: str) -> None:
    setting = db.query(AppSetting).filter_by(key=key).first()
    if setting is None:
        raise HTTPException(status_code=500, detail="Required application setting is missing")
    setting.value = value


@router.get("/health", response_model=SettingsHealthResponse)
def settings_health(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    from app.core.gmail_service import gmail_service

    encryption = get_encryption_health()

    gmail_health = gmail_service.connection_health()

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
    backup_health_keys = {
        "backup_scheduler_status",
        "backup_scheduler_failure_code",
        "backup_scheduler_last_failure_at",
        "backup_scheduler_next_retry_at",
        "backup_scheduler_failure_count",
        "backup_job_status",
        "backup_last_success_at",
        "backup_job_last_failure_at",
        "backup_job_failure_code",
        "backup_job_next_retry_at",
        "backup_job_failure_count",
    }
    backup_health = {
        setting.key: setting.value
        for setting in db.query(AppSetting)
        .filter(AppSetting.key.in_(backup_health_keys))
        .all()
    }
    scheduler_status = backup_health.get("backup_scheduler_status", "unknown")
    backup_job_status = backup_health.get("backup_job_status", "never")
    scheduler_degraded = scheduler_status == "degraded"
    backup_job_degraded = backup_job_status == "degraded"
    backup_degraded = scheduler_degraded or backup_job_degraded
    last_success_at = backup_health.get("backup_last_success_at") or (
        latest_backup["created_at"] if latest_backup else None
    )
    next_retry_at = (
        backup_health.get("backup_scheduler_next_retry_at")
        if scheduler_degraded
        else backup_health.get("backup_job_next_retry_at")
    )
    if scheduler_degraded:
        backup_message = (
            "Automatic backup protection could not start. GODFIN will retry "
            "automatically; manual backups remain available."
        )
    elif backup_job_degraded:
        backup_message = (
            "The latest automatic backup failed. The last successful backup "
            "was preserved and GODFIN will retry automatically."
        )
    elif latest_backup:
        backup_message = "Automatic backup protection is active and backups are available."
    elif scheduler_status == "operational":
        backup_message = (
            "Automatic backup protection is active. No backup has completed yet."
        )
    else:
        backup_message = "No backup has been created yet."

    last_ingest = db.query(AppSetting).filter_by(key="last_ingestion_run").first()
    network_setting = db.query(AppSetting).filter_by(key="allow_network_access").first()
    license_health = license_status(db)

    return {
        "encryption": encryption,
        "gmail": {
            **gmail_health.to_dict(),
        },
        "llm": {
            "status": llm_status,
            "provider": active_llm.provider if active_llm else None,
            "model": active_llm.model if active_llm else None,
            "message": llm_message,
        },
        "backup": {
            "status": (
                "degraded"
                if backup_degraded
                else "ok"
                if latest_backup
                else "never"
            ),
            "scheduler_status": scheduler_status,
            "job_status": backup_job_status,
            "directory": backup_dir,
            "count": len(backups),
            "last_backup": latest_backup,
            "last_success_at": last_success_at,
            "last_failure_at": (
                backup_health.get("backup_scheduler_last_failure_at")
                if scheduler_degraded
                else backup_health.get("backup_job_last_failure_at")
            ),
            "next_retry_at": next_retry_at or None,
            "failure_code": (
                backup_health.get("backup_scheduler_failure_code")
                if scheduler_degraded
                else backup_health.get("backup_job_failure_code")
            ) or None,
            "failure_count": _safe_nonnegative_int(
                backup_health.get("backup_scheduler_failure_count")
                if scheduler_degraded
                else backup_health.get("backup_job_failure_count")
            ),
            "message": backup_message,
        },
        "ingestion": {
            "status": "ok" if last_ingest and last_ingest.value else "never",
            "last_run": last_ingest.value if last_ingest else None,
        },
        "network": {
            "allow_network_access": bool(
                network_setting
                and network_setting.value.strip().lower() in {"true", "lan"}
            ),
            "message": "A restart is required after changing network access.",
        },
        "license": {
            "status": "ok" if license_health["valid"] else license_health["status"],
            "tier": license_health["tier"],
            "message": license_health["message"],
        },
    }


@router.put(
    "/preferences/timezone",
    response_model=PreferenceUpdateResponse,
)
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


@router.put(
    "/preferences/network-access",
    response_model=PreferenceUpdateResponse,
)
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
            action="enable_network_access",
            missing_detail="Enter your current PIN to make this security change",
        )
    value = "lan" if body.enabled else "local"
    _set_existing_setting(db, "allow_network_access", value)
    db.commit()
    return {
        "key": "allow_network_access",
        "value": value,
        "restart_required": True,
    }


@router.put(
    "/preferences/developer-mode",
    response_model=PreferenceUpdateResponse,
)
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
            action="enable_developer_mode",
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

class BackupCreatedResponse(BaseModel):
    filename: str
    status: Literal["success"]


@router.post("/backup", response_model=BackupCreatedResponse)
def trigger_backup(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    backup_dir = _get_backup_dir(db)
    try:
        filename = create_backup(DB_PATH, backup_dir)
        return {'filename': filename, 'status': 'success'}
    except Exception as exc:
        raise LocalOperationError(
            code="BACKUP_FAILED",
            message="GODFIN could not create the backup.",
            hint="Check the backup location and available disk space, then try again.",
        ) from exc


@router.get("/backups", response_model=list[BackupFileResponse])
def get_backups(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    backup_dir = _get_backup_dir(db)
    return list_backups(backup_dir)


class RestoreBackupRequest(BaseModel):
    pin: str = Field(..., min_length=4, max_length=8, pattern=r"^\d+$")
    confirmation: Literal["RESTORE"]


class RestoreBackupPrepared(BaseModel):
    restore_token: str
    backup_filename: str
    expires_at: str


@router.post(
    "/backups/{filename}/prepare-restore",
    response_model=RestoreBackupPrepared,
)
def prepare_backup_restore(
    filename: str,
    body: RestoreBackupRequest,
    request: Request,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Authorize one desktop-controlled restore after PIN reauthentication."""
    require_current_pin(
        db,
        body.pin,
        client_ip_from_request(request),
        action="restore_backup",
    )
    try:
        return prepare_restore_request(
            backup_dir=_get_backup_dir(db),
            filename=filename,
            request_path=default_restore_request_path(DB_PATH),
            maximum_schema_revision=CURRENT_SCHEMA_REVISION,
        )
    except Exception as exc:
        raise LocalOperationError(
            code="BACKUP_RESTORE_PREPARATION_FAILED",
            message="GODFIN could not prepare that backup for restore.",
            hint=(
                "Choose a verified GODFIN backup from this installation, "
                "then try again."
            ),
        ) from exc


# --- Developer Mode ---


class DeveloperRuleResponse(BaseModel):
    id: str
    rule_type: str
    pattern: str
    category: str
    subcategory: str | None
    priority: int
    is_system: bool


class ClassificationHealthResponse(BaseModel):
    source_counts: dict[str, int]
    avg_confidence: dict[str, float]
    unclassified_count: int
    merchant_memory_count: int
    active_rules_count: int


class DeveloperStatusResponse(BaseModel):
    developer_mode: bool
    rules: list[DeveloperRuleResponse]
    classification_health: ClassificationHealthResponse


@router.get("/developer", response_model=DeveloperStatusResponse)
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
    pattern: str = Field(..., min_length=1, max_length=1000)
    category: str = Field(..., min_length=1, max_length=100)
    subcategory: str | None = Field(default=None, max_length=100)
    priority: int = Field(default=100, ge=0, le=10_000)


class RuleUpdate(BaseModel):
    pattern: str | None = Field(default=None, min_length=1, max_length=1000)
    category: str | None = Field(default=None, min_length=1, max_length=100)
    subcategory: str | None = Field(default=None, max_length=100)
    priority: int | None = Field(default=None, ge=0, le=10_000)


class RuleUpdateResponse(BaseModel):
    id: str
    status: Literal["updated"]


@router.post(
    "/developer/rules",
    status_code=201,
    response_model=DeveloperRuleResponse,
)
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
        except re.error as exc:
            raise HTTPException(
                status_code=400,
                detail="The pattern is not valid. Check brackets and special characters.",
            ) from exc

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


@router.put(
    "/developer/rules/{rule_id}",
    response_model=RuleUpdateResponse,
)
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
            except re.error as exc:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "The pattern is not valid. Check brackets and special characters."
                    ),
                ) from exc
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
    pin: str = Field(..., min_length=4, max_length=8, pattern=r"^\d+$")
    create_backup: Literal[True] = True


class ClassificationMemoryReset(BaseModel):
    pin: str = Field(..., min_length=4, max_length=8)


class PersonalClassifierUpdate(BaseModel):
    enabled: bool


class PersonalClassifierEligibilityResponse(BaseModel):
    eligible: bool
    enabled: bool
    confirmed_corrections: int
    required_corrections: int
    category_count: int
    required_categories: int


class LearnedPatternResponse(BaseModel):
    id: str
    pattern: str
    instrument: str | None
    category: str
    subcategory: str | None
    confirmations: int
    confidence: float
    active: bool
    updated_at: str


class ClassificationCorrectionResponse(BaseModel):
    id: str
    transaction_id: str
    merchant: str
    old_category: str | None
    new_category: str
    new_subcategory: str | None
    undone: bool
    created_at: str


class MerchantMemoryResponse(BaseModel):
    id: str
    merchant: str
    category: str
    subcategory: str | None
    times_seen: int
    confidence: float


class ClassificationMemoryResponse(BaseModel):
    eligibility: PersonalClassifierEligibilityResponse
    patterns: list[LearnedPatternResponse]
    corrections: list[ClassificationCorrectionResponse]
    merchants: list[MerchantMemoryResponse]


class ClassificationUndoResponse(BaseModel):
    status: Literal["undone"]
    correction_id: str
    transaction_id: str


class ClassificationMemoryResetResponse(BaseModel):
    patterns_removed: int
    corrections_removed: int
    merchant_memories_removed: int
    backup_filename: str
    message: str


class ResetDataResponse(BaseModel):
    success: Literal[True]
    backup_created: Literal[True]
    backup_filename: str
    deleted_records: int
    deletion_counts: dict[str, int]
    message: str


@router.get(
    "/classification-memory",
    response_model=ClassificationMemoryResponse,
)
def classification_memory(
    limit: int = 100,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    from app.core.classification_learning import list_learning_memory

    return list_learning_memory(db, limit=min(max(limit, 1), 500))


@router.get(
    "/classification-memory/export",
    response_class=Response,
    responses={
        200: {
            "description": "Spreadsheet-safe classification-memory CSV.",
            "content": {"text/csv": {"schema": {"type": "string"}}},
        }
    },
)
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


@router.post(
    "/classification-memory/{correction_id}/undo",
    response_model=ClassificationUndoResponse,
)
def undo_classification_memory(
    correction_id: str,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    from app.core.classification_learning import undo_correction

    existing = db.query(ClassificationCorrection).filter_by(id=correction_id).first()
    if not existing:
        raise HTTPException(status_code=404, detail="Classification correction not found.")
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
        raise HTTPException(
            status_code=409,
            detail="This classification correction cannot be undone in its current state.",
        ) from exc


@router.put(
    "/classification-memory/personal",
    response_model=PersonalClassifierEligibilityResponse,
)
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


@router.post(
    "/classification-memory/reset",
    response_model=ClassificationMemoryResetResponse,
)
def reset_classification_memory(
    body: ClassificationMemoryReset,
    request: Request,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    from app.core.classification_learning import reset_learning_memory

    require_current_pin(
        db,
        body.pin,
        client_ip_from_request(request),
        action="reset_classification_memory",
    )
    backup_filename = create_backup(DB_PATH, _get_backup_dir(db))
    result = reset_learning_memory(db)
    db.commit()
    return {
        **result,
        "backup_filename": backup_filename,
        "message": "Classification memory reset. Existing transaction labels were preserved.",
    }


@router.post(
    "/reset-data",
    status_code=200,
    response_model=ResetDataResponse,
)
def reset_all_data(
    body: ResetDataRequest,
    request: Request,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Reset all transaction and dynamic data. PIN-protected."""
    require_current_pin(
        db,
        body.pin,
        client_ip_from_request(request),
        action="reset_all_data",
    )

    try:
        backup_filename = create_backup(DB_PATH, _get_backup_dir(db))
    except Exception as exc:
        logger.error("Safety backup failed before data reset: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Data was not reset because the safety backup failed.",
        ) from exc

    try:
        deletion_counts = reset_dynamic_data(db)
        for key in ['last_ingestion_run', 'last_gmail_history_id', 'ingestion_history']:
            setting = db.query(AppSetting).filter_by(key=key).first()
            if setting:
                setting.value = ''
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("Data reset rolled back after the safety backup succeeded")
        raise HTTPException(
            status_code=500,
            detail=(
                "Data was not reset because deletion could not be completed safely. "
                "The safety backup remains available."
            ),
        ) from exc

    deleted_records = sum(deletion_counts.values())

    return {
        'success': True,
        'backup_created': True,
        'backup_filename': backup_filename,
        'deleted_records': deleted_records,
        'deletion_counts': deletion_counts,
        'message': 'All data has been reset. Accounts and settings preserved.',
    }
