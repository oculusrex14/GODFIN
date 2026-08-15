"""System management endpoints."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Literal, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.v1.entitlements import require_entitlement
from app.core.auth import get_current_user
from app.core.config import settings as app_settings
from app.core.database import get_db
from app.core.errors import InputValidationError, StateConflictError
from app.core.pin_security import client_ip_from_request, require_current_pin
from app.models.app_setting import AppSetting

logger = logging.getLogger(__name__)
router = APIRouter()
AI_CLASSIFICATION_ENTITLEMENT = require_entitlement("ai_classification")


class SystemStatus(BaseModel):
    status: str
    version: str
    backend_url: str
    frontend_url: str


class DiagnosticApplicationStatus(BaseModel):
    version: str
    api_status: Literal["operational"]


class DiagnosticBackupStatus(BaseModel):
    status: Literal["operational", "degraded", "unknown"]
    scheduler_status: str
    job_status: str
    last_success_at: Optional[str] = None
    last_failure_at: Optional[str] = None
    next_retry_at: Optional[str] = None
    failure_code: Optional[str] = None
    failure_count: int = Field(ge=0)


class SupportDiagnostics(BaseModel):
    schema_version: Literal[2]
    generated_at_utc: str
    application: DiagnosticApplicationStatus
    backup_protection: DiagnosticBackupStatus
    readiness: dict
    background_jobs: dict
    request_metrics: dict


class LocalModelAction(BaseModel):
    model: str = Field(min_length=3, max_length=129)
    confirmed: bool = False
    current_pin: str | None = Field(
        default=None,
        min_length=4,
        max_length=8,
        pattern=r"^\d+$",
    )


class MaintenanceApproval(BaseModel):
    confirmed: bool = False
    current_pin: str | None = Field(
        default=None,
        min_length=4,
        max_length=8,
        pattern=r"^\d+$",
    )


class LocalAIChoice(BaseModel):
    choice: Literal["local", "provider", "none"]


class EmbeddingStatusResponse(BaseModel):
    enabled: bool
    status: str
    progress: int
    message: str
    updated: int
    total: int
    job_id: str | None = None
    attempt: int | None = None
    retry_at: str | None = None
    failure_code: str | None = None


class EmbeddingEnableResponse(EmbeddingStatusResponse):
    started: bool


class EmbeddingDisableResponse(BaseModel):
    enabled: Literal[False]
    cancel_requested: bool
    status: Literal["disabled"]
    message: str


class LocalAIProfileResponse(BaseModel):
    os: str
    os_version: str
    architecture: str
    processor: str
    total_ram_gb: float
    available_ram_gb: float
    memory_measurement: str
    memory_measured_at: str
    disk_free_gb: float
    acceleration: str
    ollama: dict
    recommendation: dict
    installed_model_metadata: dict | None
    readiness: dict | None
    registry: dict
    privacy: str
    installer_url: str
    context_tokens: int
    context_policy: str
    choice: str | None


class LocalAIChoiceResponse(BaseModel):
    choice: Literal["local", "provider", "none"]


class LocalAIDownloadResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: str
    model: str | None
    progress: int
    message: str
    digest: str | None
    expected_digest: str | None
    signature_verified: bool
    digest_verified: bool
    registry_version: str | None
    registry_source: str | None
    ollama_version: str | None
    approved_at: str | None
    accepted_at: str | None
    job_id: str | None
    pid: int | None
    started_at: str | None
    updated_at: str | None
    finished_at: str | None
    retryable: bool


class LocalAIBenchmarkResponse(BaseModel):
    success: bool
    model: str
    tokens_per_second: float
    elapsed_seconds: float
    response_preview: str
    prompt_kind: str
    authoritative_totals: Literal[False]
    activation_ready: bool
    context_tokens: int
    digest: str
    completed_at: str
    memory_measurement: str
    available_ram_gb: float
    disk_free_gb: float
    required_available_ram_gb: float
    required_disk_free_gb: float
    os_headroom_gb: float


class StaleMerchantResponse(BaseModel):
    id: str
    normalized_name: str
    category: str
    confidence: float
    last_updated: str | None
    times_seen: int


class StaleMerchantsResponse(BaseModel):
    merchants: list[StaleMerchantResponse]
    count: int


class SuggestedRuleResponse(BaseModel):
    pattern: str
    rule_type: str
    category: str
    subcategory: str | None
    confidence: float
    occurrences: int
    examples: list[str]


class SuggestedRulesResponse(BaseModel):
    suggestions: list[SuggestedRuleResponse]
    count: int


class GeneratedRuleResponse(BaseModel):
    pattern: str
    type: str
    category: str
    confidence: float


class AutoGenerateRulesResponse(BaseModel):
    success: Literal[True]
    created: int
    analyzed: int
    rules: list[GeneratedRuleResponse]


class MerchantMergeSuggestionResponse(BaseModel):
    primary_id: str
    primary_name: str
    primary_category: str
    primary_times_seen: int
    duplicate_id: str
    duplicate_name: str
    duplicate_category: str
    duplicate_times_seen: int
    similarity: int
    category_match: bool


class MerchantMergeSuggestionsResponse(BaseModel):
    suggestions: list[MerchantMergeSuggestionResponse]
    count: int


class DuplicateMerchantResponse(BaseModel):
    id: str
    name: str
    category: str
    similarity: int
    times_seen: int


class PrimaryMerchantResponse(BaseModel):
    id: str
    name: str
    category: str
    times_seen: int


class DuplicateGroupResponse(BaseModel):
    primary: PrimaryMerchantResponse
    duplicates: list[DuplicateMerchantResponse]


class DuplicateGroupsResponse(BaseModel):
    groups: list[DuplicateGroupResponse]
    count: int


class MerchantMergeResponse(BaseModel):
    success: Literal[True]
    primary: str
    duplicate: str
    transactions_updated: int


class SimilarMerchantResponse(BaseModel):
    id: str
    name: str
    category: str
    similarity: int
    confidence: float


class SimilarMerchantsResponse(BaseModel):
    merchant_id: str
    similar: list[SimilarMerchantResponse]
    count: int


@router.get("/status", response_model=SystemStatus)
def get_system_status(
    _user: bool = Depends(get_current_user),
):
    """Get system status."""
    return SystemStatus(
        status="ok",
        version="0.1.0",
        backend_url="http://localhost:5100",
        frontend_url="http://localhost:5200",
    )


@router.get("/diagnostics", response_model=SupportDiagnostics)
def download_support_diagnostics(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Export support-safe subsystem state without local paths or user data."""
    allowed_keys = {
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
    values = {
        setting.key: setting.value
        for setting in db.query(AppSetting)
        .filter(AppSetting.key.in_(allowed_keys))
        .all()
    }
    scheduler_status = values.get("backup_scheduler_status", "unknown")
    job_status = values.get("backup_job_status", "never")
    scheduler_degraded = scheduler_status == "degraded"
    job_degraded = job_status == "degraded"
    if scheduler_degraded or job_degraded:
        protection_status = "degraded"
    elif scheduler_status == "operational":
        protection_status = "operational"
    else:
        protection_status = "unknown"
    active_prefix = "backup_scheduler" if scheduler_degraded else "backup_job"
    try:
        failure_count = max(
            0,
            int(values.get(f"{active_prefix}_failure_count") or 0),
        )
    except (TypeError, ValueError):
        failure_count = 0

    from app.api.v1.endpoints.health import readiness_snapshot
    from app.core.background_jobs import job_queue_summary
    from app.core.local_metrics import request_metrics_snapshot

    jobs = job_queue_summary(db)
    readiness = readiness_snapshot(request, db)
    payload = {
        "schema_version": 2,
        "generated_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "application": {
            "version": app_settings.VERSION,
            "api_status": "operational",
        },
        "backup_protection": {
            "status": protection_status,
            "scheduler_status": scheduler_status,
            "job_status": job_status,
            "last_success_at": values.get("backup_last_success_at") or None,
            "last_failure_at": values.get(f"{active_prefix}_last_failure_at") or None,
            "next_retry_at": values.get(f"{active_prefix}_next_retry_at") or None,
            "failure_code": values.get(f"{active_prefix}_failure_code") or None,
            "failure_count": failure_count,
        },
        "readiness": readiness,
        "background_jobs": jobs,
        "request_metrics": request_metrics_snapshot(),
    }
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Disposition"] = (
        "attachment; filename=godfin-support-diagnostics.json"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    return SupportDiagnostics(**payload)


@router.get(
    "/embeddings/status",
    response_model=EmbeddingStatusResponse,
    response_model_exclude_unset=True,
)
def embedding_status(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    from app.core.embedding_service import get_embedding_setup_status

    setting = db.query(AppSetting).filter_by(key="enable_embeddings").first()
    enabled = bool(setting and setting.value == "true")
    status = get_embedding_setup_status()
    if not enabled:
        return {
            "enabled": False,
            "status": "disabled",
            "progress": 0,
            "message": "Embedding classification is disabled.",
            "updated": 0,
            "total": 0,
        }
    if status["status"] == "idle":
        status = {
            **status,
            "status": "enabled",
            "progress": 100,
            "message": "Embedding classification is enabled.",
        }
    return {"enabled": True, **status}


@router.post(
    "/embeddings/enable",
    status_code=202,
    dependencies=[Depends(AI_CLASSIFICATION_ENTITLEMENT)],
    response_model=EmbeddingEnableResponse,
    response_model_exclude_unset=True,
)
def enable_embeddings(
    request: Request,
    body: MaintenanceApproval = Body(default=MaintenanceApproval()),
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    from app.core.embedding_service import get_embedding_setup_status, start_embedding_setup

    if not body.confirmed:
        raise HTTPException(
            status_code=422,
            detail="Explicit model-download approval is required",
        )
    require_current_pin(
        db,
        body.current_pin,
        client_ip_from_request(request),
        action="enable_embedding_classification",
        missing_detail="Enter your current PIN to download and enable this helper",
    )
    setting = db.query(AppSetting).filter_by(key="enable_embeddings").first()
    if setting is None:
        setting = AppSetting(key="enable_embeddings", value="true")
        db.add(setting)
    else:
        setting.value = "true"
    db.commit()

    started = start_embedding_setup()
    return {
        "enabled": True,
        "started": started,
        **get_embedding_setup_status(),
    }


@router.post("/embeddings/disable", response_model=EmbeddingDisableResponse)
def disable_embeddings(
    request: Request,
    body: MaintenanceApproval = Body(default=MaintenanceApproval()),
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Disable optional matching and cancel an in-flight setup safely."""
    from app.core.embedding_service import cancel_embedding_setup

    require_current_pin(
        db,
        body.current_pin,
        client_ip_from_request(request),
        action="disable_embedding_classification",
        missing_detail="Enter your current PIN to disable this helper",
    )
    setting = db.query(AppSetting).filter_by(key="enable_embeddings").first()
    if setting is None:
        setting = AppSetting(key="enable_embeddings", value="false")
        db.add(setting)
    else:
        setting.value = "false"
    db.commit()
    cancelled = cancel_embedding_setup()
    return {
        "enabled": False,
        "cancel_requested": cancelled,
        "status": "disabled",
        "message": "Similar-description matching is disabled.",
    }


@router.get("/local-ai/profile", response_model=LocalAIProfileResponse)
def local_ai_profile(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    from app.core.local_ai import device_profile

    profile = device_profile(db=db)
    choice = db.query(AppSetting).filter_by(key="local_ai_choice").first()
    profile["choice"] = choice.value if choice else None
    return profile


@router.put("/local-ai/choice", response_model=LocalAIChoiceResponse)
def choose_local_ai(
    body: LocalAIChoice,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    setting = db.query(AppSetting).filter_by(key="local_ai_choice").first()
    if setting is None:
        setting = AppSetting(key="local_ai_choice", value=body.choice)
        db.add(setting)
    else:
        setting.value = body.choice
    db.commit()
    return {"choice": body.choice}


@router.get("/local-ai/download", response_model=LocalAIDownloadResponse)
def local_ai_download_status(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    from app.core.local_ai import restore_download_status

    return restore_download_status(db)


@router.post(
    "/local-ai/download",
    status_code=202,
    response_model=LocalAIDownloadResponse,
)
def local_ai_download(
    body: LocalModelAction,
    request: Request,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    from app.core.local_ai import (
        LocalAIActionConflict,
        LocalAIResourceError,
        start_model_pull,
    )

    if not body.confirmed:
        raise HTTPException(
            status_code=422,
            detail="Explicit model-download approval is required",
        )
    require_current_pin(
        db,
        body.current_pin,
        client_ip_from_request(request),
        action="download_local_ai_model",
        missing_detail="Enter your current PIN to start this model download",
    )
    try:
        return start_model_pull(body.model, body.confirmed)
    except ValueError as exc:
        raise InputValidationError(
            code="LOCAL_MODEL_INVALID",
            message="That local model cannot be downloaded by this GODFIN build.",
            hint="Choose a model shown in the signed compatibility list.",
        ) from exc
    except LocalAIResourceError as exc:
        raise InputValidationError(
            code="LOCAL_MODEL_CAPACITY_LOW",
            message="This device does not currently have enough free memory or disk space.",
            hint="Close other apps or free disk space, then check the device recommendation again.",
        ) from exc
    except LocalAIActionConflict as exc:
        raise StateConflictError(
            code="LOCAL_MODEL_DOWNLOAD_CONFLICT",
            message="Another local model action is already running.",
            hint="Wait for it to finish or cancel it, then try again.",
        ) from exc
    except RuntimeError as exc:
        raise StateConflictError(
            code="LOCAL_MODEL_UNAVAILABLE",
            message="The local model download could not be started safely.",
            hint="Check that Ollama is installed and running, then try again.",
        ) from exc


@router.post(
    "/local-ai/download/cancel",
    response_model=LocalAIDownloadResponse,
)
def cancel_local_ai_download(
    _user: bool = Depends(get_current_user),
):
    from app.core.local_ai import cancel_model_pull

    return cancel_model_pull()


@router.post("/local-ai/benchmark", response_model=LocalAIBenchmarkResponse)
def local_ai_benchmark(
    body: LocalModelAction,
    request: Request,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    from app.core.local_ai import LocalAIResourceError, benchmark_model

    if not body.confirmed:
        raise HTTPException(
            status_code=422,
            detail="Explicit benchmark approval is required",
        )
    require_current_pin(
        db,
        body.current_pin,
        client_ip_from_request(request),
        action="benchmark_local_ai_model",
        missing_detail="Enter your current PIN to run this benchmark",
    )
    try:
        return benchmark_model(body.model)
    except ValueError as exc:
        raise InputValidationError(
            code="LOCAL_MODEL_INVALID",
            message="That local model cannot be benchmarked by this GODFIN build.",
            hint="Choose an installed model shown in the compatibility list.",
        ) from exc
    except LocalAIResourceError as exc:
        raise HTTPException(
            status_code=409,
            detail="Current free memory or disk space is below the safe benchmark headroom.",
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=409,
            detail="A local benchmark is already running. Wait for it to finish and try again.",
        ) from exc
    except Exception as exc:
        logger.warning("Local benchmark failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail="The local benchmark could not finish. Check that Ollama is running and try again.",
        ) from exc


@router.get("/stale-merchants", response_model=StaleMerchantsResponse)
def get_stale_merchants_endpoint(
    days: int = 180,
    limit: int = 50,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Get merchants not seen in specified days."""
    from app.core.confidence_decay import get_stale_merchants

    merchants = get_stale_merchants(db, days=days, limit=limit)

    return {
        "merchants": [
            {
                "id": m.id,
                "normalized_name": m.normalized_name,
                "category": m.category,
                "confidence": m.avg_confidence,
                "last_updated": m.last_updated.isoformat() if m.last_updated else None,
                "times_seen": m.times_seen,
            }
            for m in merchants
        ],
        "count": len(merchants),
    }


@router.get("/suggested-rules", response_model=SuggestedRulesResponse)
def get_suggested_rules_endpoint(
    min_occurrences: int = 3,
    limit: int = 20,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Get suggested classification rules based on patterns."""
    from app.core.rule_generator import get_suggested_rules

    suggestions = get_suggested_rules(db, min_occurrences=min_occurrences, limit=limit)

    return {
        "suggestions": suggestions,
        "count": len(suggestions),
    }


@router.post("/auto-generate-rules", response_model=AutoGenerateRulesResponse)
def trigger_auto_generate_rules(
    min_occurrences: int = 3,
    max_rules: int = 10,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Automatically generate classification rules from patterns."""
    from app.core.rule_generator import auto_generate_rules

    result = auto_generate_rules(
        db,
        min_occurrences=min_occurrences,
        max_rules=max_rules,
    )

    return {
        "success": True,
        "created": result["created"],
        "analyzed": result["analyzed"],
        "rules": result["rules"],
    }


@router.get(
    "/merchant-merge-suggestions",
    response_model=MerchantMergeSuggestionsResponse,
)
def get_merchant_merge_suggestions(
    threshold: int = 80,
    limit: int = 20,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Get suggestions for merging similar merchant names."""
    from app.core.merchant_merging import find_merging_candidates

    suggestions = find_merging_candidates(db, threshold=threshold, max_results=limit)

    return {
        "suggestions": [
            {
                "primary_id": s.primary_id,
                "primary_name": s.primary_name,
                "primary_category": s.primary_category,
                "primary_times_seen": s.primary_times_seen,
                "duplicate_id": s.duplicate_id,
                "duplicate_name": s.duplicate_name,
                "duplicate_category": s.duplicate_category,
                "duplicate_times_seen": s.duplicate_times_seen,
                "similarity": s.similarity_score,
                "category_match": s.primary_category == s.duplicate_category,
            }
            for s in suggestions
        ],
        "count": len(suggestions),
    }


@router.get("/duplicate-groups", response_model=DuplicateGroupsResponse)
def get_duplicate_groups_endpoint(
    threshold: int = 85,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Get merchant duplicate groups for bulk merging."""
    from app.core.merchant_merging import get_duplicate_groups

    groups = get_duplicate_groups(db, threshold=threshold)

    return {
        "groups": groups,
        "count": len(groups),
    }


@router.post("/merge-merchants", response_model=MerchantMergeResponse)
def merge_merchants_endpoint(
    primary_id: str,
    duplicate_id: str,
    update_transactions: bool = True,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Merge two merchants (duplicate into primary)."""
    from app.core.merchant_merging import merge_merchants

    result = merge_merchants(
        db,
        primary_id=primary_id,
        duplicate_id=duplicate_id,
        update_transactions=update_transactions,
    )

    db.commit()

    return result


@router.get(
    "/merchants/{merchant_id}/similar",
    response_model=SimilarMerchantsResponse,
)
def get_similar_merchants(
    merchant_id: str,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Get merchants similar to a specific merchant."""
    from app.core.merchant_merging import suggest_merchant_consolidation

    suggestions = suggest_merchant_consolidation(db, merchant_id)

    return {
        "merchant_id": merchant_id,
        "similar": [
            {
                "id": s.duplicate_id,
                "name": s.duplicate_name,
                "category": s.duplicate_category,
                "similarity": s.similarity_score,
                "confidence": s.confidence,
            }
            for s in suggestions
        ],
        "count": len(suggestions),
    }
