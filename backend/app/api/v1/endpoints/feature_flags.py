from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.feature_flags import feature_flag_manifest
from app.core.opendataloader_benchmark import opendataloader_runtime_status

router = APIRouter()


@router.get("")
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
