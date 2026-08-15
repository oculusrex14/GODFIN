from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.v1.entitlements import require_entitlement
from app.core.auth import get_current_user
from app.core.behavior_insights import (
    BUDGET_KEY,
    compute_behavior_insights,
    export_behavior_insights_csv,
)
from app.core.database import get_db
from app.core.feature_flags import (
    feature_enabled,
)
from app.core.license import license_status
from app.models.app_setting import AppSetting
from app.models.behavior_insight import BehaviorInsightPreference
from app.schemas.financial import PositiveMoney

router = APIRouter()
BEHAVIOR_INSIGHTS_ENTITLEMENT = require_entitlement(
    "behavior_insights",
    "behavior_insights",
    "Behavior Insights is not available in this build.",
)


class InsightPreferenceUpdate(BaseModel):
    hidden: bool | None = None
    correction_note: str | None = Field(default=None, max_length=1000)


class BehaviorConfigUpdate(BaseModel):
    monthly_budget: PositiveMoney | None = None


class BehaviorFxMetadata(BaseModel):
    status: str
    provider: str
    source_url: str | None
    as_of: str | None
    age_days: int | None
    stale: bool | None
    rate_direction: str
    rates_to_inr: dict[str, float]
    rate_dates: dict[str, str]
    requested_currencies: list[str]
    privacy: str
    unavailable_reason: str | None


class BehaviorMetricResponse(BaseModel):
    key: str
    label: str
    value: float | None
    unit: str
    meaning: str
    formula: str
    inputs: str
    period: str
    evidence: str
    available: bool
    unavailable_reason: str | None
    sample_size: int
    minimum_sample: int
    confidence: str
    confidence_explanation: str
    provenance: str
    caveat: str
    difficulty: str
    hidden: bool
    correction_note: str | None
    currency_conversion: BehaviorFxMetadata | None = None


class BehaviorReflectionResponse(BaseModel):
    key: str
    title: str
    observation: str
    question: str
    action: str
    evidence: str
    available: bool
    unavailable_reason: str | None
    confidence: str


class BehaviorCoverageResponse(BaseModel):
    period_start: str
    period_end: str
    calendar_months: int
    calendar_month_keys: list[str]
    observed_months: int
    observed_month_keys: list[str]
    income_months: int
    spending_months: int
    cash_flow_months: int
    observed_full_weeks: int
    included_transactions: int
    current_month_excluded: bool
    note: str


class BehaviorInsightsResponse(BaseModel):
    calculation_version: str
    window_days: int
    window_months: int
    period: str
    coverage: BehaviorCoverageResponse
    metrics: list[BehaviorMetricResponse]
    reflections: list[BehaviorReflectionResponse]
    monthly_budget: float | None
    policy: str


class SponsorMessageResponse(BaseModel):
    label: str
    title: str
    body: str
    href: str | None


class SponsorCardResponse(BaseModel):
    visible: bool
    placement: str
    personalized: bool
    third_party_scripts: bool
    uses_financial_data: bool
    sponsor: SponsorMessageResponse | None


@router.get(
    "",
    dependencies=[Depends(BEHAVIOR_INSIGHTS_ENTITLEMENT)],
    response_model=BehaviorInsightsResponse,
    response_model_exclude_unset=True,
)
def insights(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    return compute_behavior_insights(db)


@router.put(
    "/config",
    dependencies=[Depends(BEHAVIOR_INSIGHTS_ENTITLEMENT)],
    response_model=BehaviorInsightsResponse,
    response_model_exclude_unset=True,
)
def update_config(
    body: BehaviorConfigUpdate,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    setting = db.query(AppSetting).filter_by(key=BUDGET_KEY).first()
    value = "" if body.monthly_budget is None else str(body.monthly_budget)
    if setting:
        setting.value = value
    else:
        db.add(AppSetting(key=BUDGET_KEY, value=value))
    db.commit()
    return compute_behavior_insights(db)


@router.put(
    "/{metric_key}",
    dependencies=[Depends(BEHAVIOR_INSIGHTS_ENTITLEMENT)],
    response_model=BehaviorInsightsResponse,
    response_model_exclude_unset=True,
)
def update_preference(
    metric_key: str,
    body: InsightPreferenceUpdate,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    valid_keys = {
        metric["key"] for metric in compute_behavior_insights(db)["metrics"]
    }
    if metric_key not in valid_keys:
        raise HTTPException(status_code=404, detail="Insight metric not found.")
    preference = (
        db.query(BehaviorInsightPreference).filter_by(metric_key=metric_key).first()
    )
    if preference is None:
        preference = BehaviorInsightPreference(metric_key=metric_key)
        db.add(preference)
    if body.hidden is not None:
        preference.hidden = body.hidden
    if body.correction_note is not None:
        preference.correction_note = body.correction_note.strip() or None
    db.commit()
    return compute_behavior_insights(db)


@router.post(
    "/reset",
    dependencies=[Depends(BEHAVIOR_INSIGHTS_ENTITLEMENT)],
    response_model=BehaviorInsightsResponse,
    response_model_exclude_unset=True,
)
def reset_preferences(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    db.query(BehaviorInsightPreference).delete(synchronize_session=False)
    budget = db.query(AppSetting).filter_by(key=BUDGET_KEY).first()
    if budget:
        budget.value = ""
    db.commit()
    return compute_behavior_insights(db)


@router.get(
    "/export",
    dependencies=[Depends(BEHAVIOR_INSIGHTS_ENTITLEMENT)],
    response_class=Response,
    responses={
        200: {
            "description": "Spreadsheet-safe behavior-insight CSV export.",
            "content": {"text/csv": {"schema": {"type": "string"}}},
        }
    },
)
def export_insights(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    return Response(
        content=export_behavior_insights_csv(db),
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=godfin-behavior-insights.csv"
        },
    )


@router.get("/sponsor/card", response_model=SponsorCardResponse)
def sponsor_card(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    status = license_status(db)
    visible = feature_enabled(db, "sponsor_card") and status["tier"] == "free"
    return {
        "visible": visible,
        "placement": "behavior_insights_bottom",
        "personalized": False,
        "third_party_scripts": False,
        "uses_financial_data": False,
        "sponsor": (
            {
                "label": "Sponsor",
                "title": "GODFIN partner message",
                "body": "A quiet, non-personalized message helps support GODFIN Core.",
                "href": None,
            }
            if visible
            else None
        ),
    }
