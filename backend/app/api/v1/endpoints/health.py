from __future__ import annotations

import os
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.background_jobs import job_queue_summary
from app.core.config import settings
from app.core.database import get_db
from app.core.startup_migrations import CURRENT_SCHEMA_REVISION
from app.models.app_setting import AppSetting

router = APIRouter()


class HealthResponse(BaseModel):
    status: Literal["alive"]
    liveness: bool
    database: Literal["not_checked"]
    version: str


class ReadinessDependencies(BaseModel):
    database: str
    schema_status: str = Field(alias="schema")
    schema_revision: Optional[int] = None
    expected_schema_revision: int
    lifecycle: str
    scheduler: str
    background_worker: str


class ReadinessJobs(BaseModel):
    active: int
    capacity: int
    worker_running: bool


class ReadinessResponse(BaseModel):
    status: Literal["ready", "degraded", "unavailable"]
    ready: bool
    version: str
    dependencies: ReadinessDependencies
    background_jobs: ReadinessJobs


@router.get("/health", response_model=HealthResponse)
def health_check():
    """Process liveness only; dependencies are assessed by /ready."""
    return {
        "status": "alive",
        "liveness": True,
        "database": "not_checked",
        "version": settings.VERSION,
    }


def readiness_snapshot(request: Request, db: Session) -> dict[str, Any]:
    database_status = "connected"
    schema_revision: int | None = None
    try:
        db.execute(text("SELECT 1"))
        revision = db.query(AppSetting).filter_by(key="schema_revision").first()
        if revision is not None:
            schema_revision = int(revision.value)
    except Exception:
        db.rollback()
        database_status = "unavailable"

    testing = os.environ.get("GODFIN_TESTING") == "1"
    lifecycle = getattr(request.app.state, "lifecycle_status", "test" if testing else "unknown")
    scheduler = getattr(request.app.state, "scheduler_status", "test" if testing else "unknown")
    job_worker = getattr(request.app.state, "job_worker_status", "test" if testing else "unknown")
    try:
        jobs = job_queue_summary(db)
    except Exception:
        db.rollback()
        jobs = {
            "active": 0,
            "capacity": 0,
            "worker_running": False,
            "counts": {},
            "registered_kinds": [],
            "oldest_active_at": None,
        }

    schema_status = (
        "current"
        if schema_revision == CURRENT_SCHEMA_REVISION
        else "unknown" if schema_revision is None else "mismatch"
    )
    ready = bool(
        database_status == "connected"
        and lifecycle in {"ready", "test"}
        and schema_status != "mismatch"
    )
    optional_degraded = scheduler == "degraded" or job_worker == "degraded"
    return {
        "status": "ready" if ready and not optional_degraded else "degraded" if ready else "unavailable",
        "ready": ready,
        "version": settings.VERSION,
        "dependencies": {
            "database": database_status,
            "schema": schema_status,
            "schema_revision": schema_revision,
            "expected_schema_revision": CURRENT_SCHEMA_REVISION,
            "lifecycle": lifecycle,
            "scheduler": scheduler,
            "background_worker": job_worker,
        },
        "background_jobs": {
            "active": jobs["active"],
            "capacity": jobs["capacity"],
            "worker_running": jobs["worker_running"],
        },
    }


@router.get("/ready", response_model=ReadinessResponse)
def readiness_check(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """Critical readiness plus explicitly nonessential subsystem health."""
    payload = readiness_snapshot(request, db)
    if not payload["ready"]:
        response.status_code = 503
    response.headers["Cache-Control"] = "no-store"
    return payload
