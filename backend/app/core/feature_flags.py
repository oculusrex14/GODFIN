from __future__ import annotations

import os
from typing import Final

from sqlalchemy.orm import Session

from app.models.app_setting import AppSetting


FEATURE_DEFAULTS: Final[dict[str, bool]] = {
    "local_ai": True,
    "behavior_insights": True,
    "reward_pilot": False,
    "sponsor_card": False,
    "net_worth": True,
    "opendataloader_benchmark": False,
}


class FeatureDisabledError(RuntimeError):
    pass


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def feature_enabled(db: Session, feature: str) -> bool:
    if feature not in FEATURE_DEFAULTS:
        return False
    environment = os.environ.get(f"GODFIN_FEATURE_{feature.upper()}")
    if environment is not None:
        return _parse_bool(environment, FEATURE_DEFAULTS[feature])
    setting = db.query(AppSetting).filter_by(key=f"feature_{feature}").first()
    return _parse_bool(
        setting.value if setting else None,
        FEATURE_DEFAULTS[feature],
    )


def require_feature_flag(db: Session, feature: str) -> None:
    if feature_enabled(db, feature):
        return
    raise FeatureDisabledError(
        f"{feature.replace('_', ' ').title()} is not enabled in this build."
    )


def feature_flag_manifest(db: Session) -> dict[str, bool]:
    return {name: feature_enabled(db, name) for name in FEATURE_DEFAULTS}
