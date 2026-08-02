"""System management endpoints."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.app_setting import AppSetting

logger = logging.getLogger(__name__)
router = APIRouter()


class SystemStatus(BaseModel):
    status: str
    version: str
    backend_url: str
    frontend_url: str


class RestartResponse(BaseModel):
    message: str
    restarting: bool


class LocalModelAction(BaseModel):
    model: str = Field(min_length=3, max_length=129)
    confirmed: bool = False


class LocalAIChoice(BaseModel):
    choice: Literal["local", "provider", "none"]


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


@router.post("/restart", response_model=RestartResponse)
def restart_backend(
    _user: bool = Depends(get_current_user),
):
    """
    Restart the backend server.
    Triggers a clean shutdown and restart via external script.
    """
    try:
        # Get the backend directory (4 levels up from this file)
        current_file = Path(__file__).resolve()
        backend_dir = current_file.parents[4]
        restart_script = backend_dir / "restart.sh"
        log_file = backend_dir / "logs" / "restart.log"

        if not restart_script.exists():
            logger.error(f"Restart script not found: {restart_script}")
            return RestartResponse(
                message=f"Restart script not found: {restart_script}",
                restarting=False,
            )

        # Make sure script is executable
        restart_script.chmod(0o755)

        def delayed_restart():
            """Execute restart after response is sent."""
            time.sleep(1)  # Give time for response to be sent
            try:
                # Start the restart script, keeping stdout/stderr connected
                # so logs appear in the original terminal
                subprocess.Popen(
                    [str(restart_script)],
                    stdout=None,  # Inherit parent's stdout
                    stderr=None,  # Inherit parent's stderr
                    stdin=subprocess.DEVNULL,
                    cwd=str(backend_dir),
                )
                logger.info("Restart script launched successfully")
            except Exception as e:
                logger.error(f"Failed to launch restart script: {e}")

        # Start restart in background thread
        thread = threading.Thread(target=delayed_restart, daemon=True)
        thread.start()

        logger.info("Backend restart initiated")
        return RestartResponse(
            message="Backend restart initiated. The server will restart in 3-5 seconds. Please wait before refreshing.",
            restarting=True,
        )
    except Exception as e:
        logger.error(f"Failed to initiate restart: {e}")
        return RestartResponse(
            message=f"Failed to restart: {str(e)}",
            restarting=False,
        )


@router.post("/backfill-embeddings")
def trigger_backfill_embeddings(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Backfill embeddings for all merchants without embeddings."""
    from app.api.v1.endpoints.license import enforce_feature

    enforce_feature(db, "ai_classification")
    from app.core.embedding_service import backfill_embeddings

    updated = backfill_embeddings(db)
    db.commit()

    return {
        "success": True,
        "updated": updated,
        "message": f"Backfilled embeddings for {updated} merchants",
    }


@router.get("/embeddings/status")
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


@router.post("/embeddings/enable", status_code=202)
def enable_embeddings(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    from app.api.v1.endpoints.license import enforce_feature
    from app.core.embedding_service import get_embedding_setup_status, start_embedding_setup

    enforce_feature(db, "ai_classification")
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


@router.get("/local-ai/profile")
def local_ai_profile(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    from app.core.local_ai import device_profile

    profile = device_profile()
    choice = db.query(AppSetting).filter_by(key="local_ai_choice").first()
    profile["choice"] = choice.value if choice else None
    return profile


@router.put("/local-ai/choice")
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


@router.get("/local-ai/download")
def local_ai_download_status(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    from app.core.local_ai import restore_download_status

    return restore_download_status(db)


@router.post("/local-ai/download", status_code=202)
def local_ai_download(
    body: LocalModelAction,
    _user: bool = Depends(get_current_user),
):
    from app.core.local_ai import start_model_pull

    try:
        return start_model_pull(body.model, body.confirmed)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/local-ai/download/cancel")
def cancel_local_ai_download(
    _user: bool = Depends(get_current_user),
):
    from app.core.local_ai import cancel_model_pull

    return cancel_model_pull()


@router.post("/local-ai/benchmark")
def local_ai_benchmark(
    body: LocalModelAction,
    _user: bool = Depends(get_current_user),
):
    from app.core.local_ai import benchmark_model

    if not body.confirmed:
        raise HTTPException(
            status_code=422,
            detail="Explicit benchmark approval is required",
        )
    try:
        return benchmark_model(body.model)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Local benchmark failed: {exc}",
        ) from exc


@router.post("/apply-confidence-decay")
def trigger_confidence_decay(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Apply confidence decay to merchants not seen in 6+ months."""
    from app.core.confidence_decay import apply_confidence_decay

    updated = apply_confidence_decay(db)

    return {
        "success": True,
        "updated": updated,
        "message": f"Applied confidence decay to {updated} merchants",
    }


@router.get("/stale-merchants")
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


@router.get("/suggested-rules")
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


@router.post("/auto-generate-rules")
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


@router.get("/merchant-merge-suggestions")
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


@router.get("/duplicate-groups")
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


@router.post("/merge-merchants")
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


@router.get("/merchants/{merchant_id}/similar")
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
