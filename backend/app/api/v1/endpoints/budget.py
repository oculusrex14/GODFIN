from __future__ import annotations

from datetime import date, datetime
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
from app.core.recurring import detect_recurring_patterns
from app.models.goal import Goal
from app.models.recurring_pattern import RecurringPattern

router = APIRouter()


# --- Schemas ---

class GoalCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    target_amount: float = Field(..., gt=0)
    deadline_date: str = Field(..., pattern=r'^\d{4}-\d{2}-\d{2}$')
    pressure_level: str = Field(default='moderate', pattern=r'^(minimal|moderate|aggressive)$')
    annual_return_rate: float = Field(default=0.035, ge=0, le=0.5)
    minimum_flexible_floor: float = Field(default=5000, ge=0)


class GoalUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    target_amount: Optional[float] = Field(None, gt=0)
    current_saved: Optional[float] = Field(None, ge=0)
    deadline_date: Optional[str] = Field(None, pattern=r'^\d{4}-\d{2}-\d{2}$')
    pressure_level: Optional[str] = Field(None, pattern=r'^(minimal|moderate|aggressive)$')
    is_active: Optional[bool] = None


# --- Goals ---

@router.get("/goals")
def list_goals(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    goals = db.query(Goal).filter_by(is_active=True).all()
    return [
        {
            "id": g.id,
            "name": g.name,
            "target_amount": g.target_amount,
            "current_saved": g.current_saved,
            "deadline_date": str(g.deadline_date),
            "pressure_level": g.pressure_level,
            "annual_return_rate": g.annual_return_rate,
            "minimum_flexible_floor": g.minimum_flexible_floor,
            "is_active": g.is_active,
        }
        for g in goals
    ]


@router.post("/goals", status_code=201)
def create_goal(
    body: GoalCreate,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    deadline = date.fromisoformat(body.deadline_date)
    if deadline <= date.today():
        raise HTTPException(status_code=400, detail="Deadline must be in the future")

    goal = Goal(
        name=body.name,
        target_amount=body.target_amount,
        deadline_date=deadline,
        pressure_level=body.pressure_level,
        annual_return_rate=body.annual_return_rate,
        minimum_flexible_floor=body.minimum_flexible_floor,
    )
    db.add(goal)
    db.commit()
    db.refresh(goal)

    return {
        "id": goal.id,
        "name": goal.name,
        "target_amount": goal.target_amount,
        "deadline_date": str(goal.deadline_date),
    }


@router.put("/goals/{goal_id}")
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
        goal.current_saved = body.current_saved
    if body.deadline_date is not None:
        goal.deadline_date = date.fromisoformat(body.deadline_date)
    if body.pressure_level is not None:
        goal.pressure_level = body.pressure_level
    if body.is_active is not None:
        goal.is_active = body.is_active

    db.commit()
    return {"id": goal.id, "status": "updated"}


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


@router.post("/goals/{goal_id}/simulate")
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
    }


# --- Recurring ---

@router.get("/recurring")
def list_recurring(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    patterns = db.query(RecurringPattern).filter_by(is_active=True).all()
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
        }
        for p in patterns
    ]


@router.post("/recurring/detect")
def trigger_detection(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    detected = detect_recurring_patterns(db)
    db.commit()
    return {"detected": detected}


# --- Financial Profile ---

@router.get("/profile")
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
    }


# --- Elasticity ---

@router.get("/elasticity")
def get_elasticity(
    _user: bool = Depends(get_current_user),
):
    return ELASTICITY
