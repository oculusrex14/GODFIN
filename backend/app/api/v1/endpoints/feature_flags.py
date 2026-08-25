from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.feature_flags import feature_flag_manifest
from app.core.opendataloader_benchmark import opendataloader_runtime_status

router = APIRouter()


class FeatureFlagValues(BaseModel):
    local_ai: bool
    behavior_insights: bool
    reward_pilot: bool
    sponsor_card: bool
    net_worth: bool
    opendataloader_benchmark: bool


class OpenDataLoaderStatus(BaseModel):
    java_available: bool
    java_path: str | None
    package_available: bool
    ready: bool
    shipped: bool
    reason: str


class ExtractorStatus(BaseModel):
    current: str
    opendataloader: OpenDataLoaderStatus


class FeatureFlagsResponse(BaseModel):
    features: FeatureFlagValues
    extractors: ExtractorStatus


@router.get("", response_model=FeatureFlagsResponse)
def flags(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    return {
        "features": feature_flag_manifest(db),
        "extractors": {
            "current": "godfin_native",
            "opendataloader": opendataloader_runtime_status(),
        },
    }
