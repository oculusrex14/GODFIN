from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.budget import (
    ELASTICITY,
    compute_financial_profile,
    simulate_goal,
)
from app.core.database import get_db
from app.core.errors import InvalidOperationError, StateConflictError
from app.core.goal_contributions import (
    add_goal_contribution,
    assign_goal_contribution_suggestion,
    calculate_goal_balance,
    contribution_to_dict,
    recompute_goal_balance,
    suggestion_to_dict,
    void_goal_contribution,
)
from app.core.license import has_feature
from app.core.product_depth import sync_subscription_suggestions
from app.core.recurring import detect_recurring_patterns
from app.models.goal import Goal
from app.models.goal_contribution import (
    GoalContribution,
    GoalContributionSuggestion,
)
from app.models.recurring_pattern import RecurringPattern
from app.models.transaction import Transaction
from app.schemas.financial import (
    ExpectedAnnualReturnRate,
    GoalContributionType,
    GoalPressureLevel,
    NonNegativeMoney,
    PastOrTodayDate,
    PositiveMoney,
)

router = APIRouter()


# --- Schemas ---

class GoalCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    target_amount: PositiveMoney
    deadline_date: date
    pressure_level: GoalPressureLevel = 'moderate'
    current_saved: NonNegativeMoney = 0
    annual_return_rate: ExpectedAnnualReturnRate = 0
    minimum_flexible_floor: NonNegativeMoney = 5000


class GoalUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    target_amount: Optional[PositiveMoney] = None
    current_saved: Optional[NonNegativeMoney] = None
    deadline_date: Optional[date] = None
    pressure_level: Optional[GoalPressureLevel] = None
    annual_return_rate: Optional[ExpectedAnnualReturnRate] = None
    minimum_flexible_floor: Optional[NonNegativeMoney] = None
    is_active: Optional[bool] = None


class GoalContributionCreate(BaseModel):
    amount: PositiveMoney
    entry_type: GoalContributionType
    contribution_date: Optional[PastOrTodayDate] = None
    note: Optional[str] = Field(None, max_length=255)
    idempotency_key: Optional[str] = Field(None, min_length=1, max_length=100)


class GoalContributionVoid(BaseModel):
    reason: str = Field(..., min_length=1, max_length=255)


class GoalSuggestionDecision(BaseModel):
    goal_id: Optional[str] = Field(default=None, min_length=1, max_length=36)


class GoalResponse(BaseModel):
    id: str
    name: str
    target_amount: float
    current_saved: float
    deadline_date: str
    pressure_level: str
    annual_return_rate: float
    minimum_flexible_floor: float
    is_active: bool
    contribution_count: int
    pending_suggestion_count: int


class GoalCreatedResponse(BaseModel):
    id: str
    name: str
    target_amount: float
    current_saved: float
    deadline_date: str


class GoalUpdatedResponse(BaseModel):
    id: str
    status: str


class GoalContributionResponse(BaseModel):
    id: str
    goal_id: str
    amount: float
    contribution_date: str
    entry_type: str
    source_type: str
    source_transaction_id: str | None
    note: str | None
    is_voided: bool
    voided_at: str | None
    void_reason: str | None
    created_at: str


class GoalBalanceUpdateResponse(BaseModel):
    contribution: GoalContributionResponse
    current_saved: float


class GoalSuggestionResponse(BaseModel):
    id: str
    transaction_id: str
    goal_id: str | None
    amount: float
    deposit_type: str
    evidence: str
    confidence: float
    status: str
    decision_note: str | None
    transaction_date: str | None
    merchant: str | None


class GoalSuggestionListResponse(BaseModel):
    enabled: bool
    items: list[GoalSuggestionResponse]


class GoalSuggestionDecisionResponse(BaseModel):
    suggestion: GoalSuggestionResponse
    contribution: GoalContributionResponse | None
    current_saved: float | None


class SimulationAssumptionsResponse(BaseModel):
    contribution_timing: str
    schedule_basis: str
    first_contribution_date: str | None
    last_contribution_date: str | None
    scheduled_contribution_count: int
    amount_due_before_first_month_end: bool
    annual_return_rate: float
    monthly_return_rate: float
    minimum_flexible_floor: float
    history_window_months: int
    minimum_complete_months: int
    existing_savings_compounded_separately: bool


class GoalSimulationResponse(BaseModel):
    required_monthly: float
    flexible_spend: float
    max_saveable: float
    is_feasible: bool | None
    months_remaining: int
    extended_deadline_months: int | None
    pressure_savings: dict[str, float]
    baseline_surplus: float
    reducible_flexible_spend: float
    coverage_months: int
    coverage_start: str | None
    coverage_end: str | None
    capacity_status: str
    calculation_version: str
    assumptions: SimulationAssumptionsResponse
    caveat: str


class RecurringPatternResponse(BaseModel):
    id: str
    merchant: str
    avg_amount: float
    frequency: str
    category: str | None
    last_occurrence: str | None
    next_expected: str | None
    times_detected: int
    confidence: float
    evidence_count: int
    detection_status: str
    review_required: bool


class RecurringDetectionResponse(BaseModel):
    detected: int
    created: int
    updated: int
    deactivated: int
    scanned: int
    subscription_suggestions_created: int


class FinancialProfileResponse(BaseModel):
    impulse_index: float | None
    lifestyle_inflation: float | None
    fixed_expense_ratio: float | None
    recurring_burden: float | None
    subscription_dependency: float | None
    savings_rate: float | None
    data_status: str
    period_start: str | None
    period_end: str | None
    comparison_start: str | None
    comparison_end: str | None
    transaction_count: int
    comparison_transaction_count: int
    calculation_version: str
    caveat: str


# --- Goals ---

@router.get("/goals", response_model=list[GoalResponse])
def list_goals(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    goals = db.query(Goal).filter_by(is_active=True).all()
    response = []
    for g in goals:
        current_saved = calculate_goal_balance(db, g.id)
        response.append({
            "id": g.id,
            "name": g.name,
            "target_amount": g.target_amount,
            "current_saved": current_saved,
            "deadline_date": str(g.deadline_date),
            "pressure_level": g.pressure_level,
            "annual_return_rate": g.annual_return_rate,
            "minimum_flexible_floor": g.minimum_flexible_floor,
            "is_active": g.is_active,
            "contribution_count": (
                db.query(GoalContribution)
                .filter_by(goal_id=g.id, is_voided=False)
                .count()
            ),
            "pending_suggestion_count": (
                db.query(GoalContributionSuggestion)
                .filter_by(goal_id=g.id, status="pending")
                .count()
            ),
        })
    return response


@router.post("/goals", response_model=GoalCreatedResponse, status_code=201)
def create_goal(
    body: GoalCreate,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    deadline = body.deadline_date
    if deadline <= date.today():
        raise HTTPException(status_code=400, detail="Deadline must be in the future")

    goal = Goal(
        name=body.name,
        target_amount=body.target_amount,
        current_saved=0,
        deadline_date=deadline,
        pressure_level=body.pressure_level,
        annual_return_rate=body.annual_return_rate,
        minimum_flexible_floor=body.minimum_flexible_floor,
    )
    db.add(goal)
    db.flush()
    if body.current_saved > 0:
        add_goal_contribution(
            db,
            goal,
            amount=body.current_saved,
            entry_type="deposit",
            contribution_date=date.today(),
            source_type="opening_balance",
            idempotency_key=f"opening:{goal.id}",
            note="Opening balance entered when the goal was created.",
        )
    db.commit()
    db.refresh(goal)

    return {
        "id": goal.id,
        "name": goal.name,
        "target_amount": goal.target_amount,
        "current_saved": goal.current_saved,
        "deadline_date": str(goal.deadline_date),
    }


@router.put("/goals/{goal_id}", response_model=GoalUpdatedResponse)
def update_goal(
    goal_id: str,
    body: GoalUpdate,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    goal = db.query(Goal).filter_by(id=goal_id).first()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")

    if body.name is not None:
        goal.name = body.name
    if body.target_amount is not None:
        goal.target_amount = body.target_amount
    if body.current_saved is not None:
        current = recompute_goal_balance(db, goal)
        difference = round(body.current_saved - current, 2)
        if abs(difference) >= 0.01:
            try:
                add_goal_contribution(
                    db,
                    goal,
                    amount=abs(difference),
                    entry_type="deposit" if difference > 0 else "withdrawal",
                    contribution_date=date.today(),
                    source_type="compatibility_adjustment",
                    note="Balance adjustment from goal edit.",
                )
            except ValueError as exc:
                raise InvalidOperationError(
                    code="GOAL_BALANCE_INVALID",
                    message="That savings balance change is not valid for this goal.",
                    hint="Check the amount and try again.",
                ) from exc
    if body.deadline_date is not None:
        if body.deadline_date <= date.today():
            raise HTTPException(status_code=400, detail="Deadline must be in the future")
        goal.deadline_date = body.deadline_date
    if body.pressure_level is not None:
        goal.pressure_level = body.pressure_level
    if body.annual_return_rate is not None:
        goal.annual_return_rate = body.annual_return_rate
    if body.minimum_flexible_floor is not None:
        goal.minimum_flexible_floor = body.minimum_flexible_floor
    if body.is_active is not None:
        goal.is_active = body.is_active

    db.commit()
    return {"id": goal.id, "status": "updated"}


@router.get(
    "/goals/{goal_id}/contributions",
    response_model=list[GoalContributionResponse],
)
def list_goal_contributions(
    goal_id: str,
    include_voided: bool = False,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    goal = db.query(Goal).filter_by(id=goal_id).first()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    query = db.query(GoalContribution).filter_by(goal_id=goal_id)
    if not include_voided:
        query = query.filter_by(is_voided=False)
    entries = query.order_by(
        GoalContribution.contribution_date.desc(),
        GoalContribution.created_at.desc(),
    ).all()
    return [contribution_to_dict(entry) for entry in entries]


@router.post(
    "/goals/{goal_id}/contributions",
    response_model=GoalBalanceUpdateResponse,
    status_code=201,
)
def create_goal_contribution(
    goal_id: str,
    body: GoalContributionCreate,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    goal = db.query(Goal).filter_by(id=goal_id, is_active=True).first()
    if not goal:
        raise HTTPException(status_code=404, detail="Active goal not found")
    try:
        entry = add_goal_contribution(
            db,
            goal,
            amount=body.amount,
            entry_type=body.entry_type,
            contribution_date=body.contribution_date or date.today(),
            note=body.note,
            idempotency_key=body.idempotency_key,
        )
    except ValueError as exc:
        raise InvalidOperationError(
            code="GOAL_CONTRIBUTION_INVALID",
            message="That savings update is not valid.",
            hint="Check the amount, type, and date, then try again.",
        ) from exc
    db.commit()
    db.refresh(entry)
    return {
        "contribution": contribution_to_dict(entry),
        "current_saved": goal.current_saved,
    }


@router.post(
    "/goals/{goal_id}/contributions/{contribution_id}/void",
    response_model=GoalBalanceUpdateResponse,
)
def void_contribution(
    goal_id: str,
    contribution_id: str,
    body: GoalContributionVoid,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    entry = (
        db.query(GoalContribution)
        .filter_by(id=contribution_id, goal_id=goal_id)
        .first()
    )
    if not entry:
        raise HTTPException(status_code=404, detail="Contribution not found")
    try:
        void_goal_contribution(db, entry, reason=body.reason)
    except ValueError as exc:
        raise StateConflictError(
            code="GOAL_CONTRIBUTION_CONFLICT",
            message="That savings entry cannot be voided in its current state.",
        ) from exc
    goal = db.query(Goal).filter_by(id=goal_id).one()
    db.commit()
    return {
        "contribution": contribution_to_dict(entry),
        "current_saved": goal.current_saved,
    }


@router.get(
    "/goal-contribution-suggestions",
    response_model=GoalSuggestionListResponse,
)
def list_goal_contribution_suggestions(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    enabled = has_feature(db, "fd_rd_goal_detection")
    if not enabled:
        return {"enabled": False, "items": []}
    suggestions = (
        db.query(GoalContributionSuggestion)
        .filter_by(status="pending")
        .order_by(GoalContributionSuggestion.created_at.desc())
        .all()
    )
    transactions = {
        transaction.id: transaction
        for transaction in db.query(Transaction)
        .filter(
            Transaction.id.in_(
                [suggestion.transaction_id for suggestion in suggestions]
            )
        )
        .all()
    } if suggestions else {}
    return {
        "enabled": True,
        "items": [
            suggestion_to_dict(
                suggestion,
                transactions.get(suggestion.transaction_id),
            )
            for suggestion in suggestions
        ],
    }


@router.post(
    "/goal-contribution-suggestions/{suggestion_id}/decision",
    response_model=GoalSuggestionDecisionResponse,
)
def decide_goal_contribution_suggestion(
    suggestion_id: str,
    body: GoalSuggestionDecision,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    if not has_feature(db, "fd_rd_goal_detection"):
        raise HTTPException(
            status_code=403,
            detail="FD/RD goal detection requires GODFIN Pro or Max.",
        )
    suggestion = (
        db.query(GoalContributionSuggestion).filter_by(id=suggestion_id).first()
    )
    if not suggestion:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    goal = None
    if body.goal_id:
        goal = (
            db.query(Goal)
            .filter_by(id=body.goal_id, is_active=True)
            .first()
        )
        if not goal:
            raise HTTPException(status_code=404, detail="Active goal not found")
    try:
        contribution = assign_goal_contribution_suggestion(
            db, suggestion, goal=goal
        )
    except ValueError as exc:
        raise InvalidOperationError(
            code="GOAL_SUGGESTION_INVALID",
            message="That detected deposit cannot be assigned as requested.",
            hint="Refresh the suggestion and choose an active goal or None.",
        ) from exc
    db.commit()
    return {
        "suggestion": suggestion_to_dict(suggestion),
        "contribution": (
            contribution_to_dict(contribution) if contribution else None
        ),
        "current_saved": goal.current_saved if goal else None,
    }


@router.delete("/goals/{goal_id}", status_code=204)
def delete_goal(
    goal_id: str,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    goal = db.query(Goal).filter_by(id=goal_id).first()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")

    goal.is_active = False
    db.commit()


@router.post("/goals/{goal_id}/simulate", response_model=GoalSimulationResponse)
def simulate(
    goal_id: str,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    goal = db.query(Goal).filter_by(id=goal_id).first()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")

    result = simulate_goal(
        db,
        target_amount=goal.target_amount,
        current_saved=goal.current_saved,
        deadline=goal.deadline_date,
        annual_return_rate=goal.annual_return_rate,
        minimum_floor=goal.minimum_flexible_floor,
    )

    return {
        "required_monthly": result.required_monthly,
        "flexible_spend": result.flexible_spend,
        "max_saveable": result.max_saveable,
        "is_feasible": result.is_feasible,
        "months_remaining": result.months_remaining,
        "extended_deadline_months": result.extended_deadline_months,
        "pressure_savings": result.pressure_savings,
        "baseline_surplus": result.baseline_surplus,
        "reducible_flexible_spend": result.reducible_flexible_spend,
        "coverage_months": result.coverage_months,
        "coverage_start": result.coverage_start,
        "coverage_end": result.coverage_end,
        "capacity_status": result.capacity_status,
        "calculation_version": result.calculation_version,
        "assumptions": result.assumptions,
        "caveat": result.caveat,
    }


# --- Recurring ---

@router.get("/recurring", response_model=list[RecurringPatternResponse])
def list_recurring(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    patterns = (
        db.query(RecurringPattern)
        .filter(
            RecurringPattern.detection_status.in_(["active", "candidate"])
        )
        .all()
    )
    return [
        {
            "id": p.id,
            "merchant": p.merchant_normalized,
            "avg_amount": p.avg_amount,
            "frequency": p.frequency,
            "category": p.category,
            "last_occurrence": str(p.last_occurrence) if p.last_occurrence else None,
            "next_expected": str(p.next_expected) if p.next_expected else None,
            "times_detected": p.times_detected,
            "confidence": p.confidence,
            "evidence_count": p.evidence_count,
            "detection_status": p.detection_status,
            "review_required": p.detection_status == "candidate",
        }
        for p in patterns
    ]


@router.post("/recurring/detect", response_model=RecurringDetectionResponse)
def trigger_detection(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    summary = detect_recurring_patterns(db)
    suggestions_created = sync_subscription_suggestions(
        db, run_detection=False
    )
    db.commit()
    return {
        **summary.to_dict(),
        "subscription_suggestions_created": suggestions_created,
    }


# --- Financial Profile ---

@router.get("/profile", response_model=FinancialProfileResponse)
def financial_profile(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    profile = compute_financial_profile(db)
    return {
        "impulse_index": profile.impulse_index,
        "lifestyle_inflation": profile.lifestyle_inflation,
        "fixed_expense_ratio": profile.fixed_expense_ratio,
        "recurring_burden": profile.recurring_burden,
        "subscription_dependency": profile.subscription_dependency,
        "savings_rate": profile.savings_rate,
        "data_status": profile.data_status,
        "period_start": profile.period_start,
        "period_end": profile.period_end,
        "comparison_start": profile.comparison_start,
        "comparison_end": profile.comparison_end,
        "transaction_count": profile.transaction_count,
        "comparison_transaction_count": profile.comparison_transaction_count,
        "calculation_version": profile.calculation_version,
        "caveat": profile.caveat,
    }


# --- Elasticity ---

@router.get("/elasticity", response_model=dict[str, str])
def get_elasticity(
    _user: bool = Depends(get_current_user),
):
    return ELASTICITY
