"""Financial Advisor AI service — builds user profile and handles chat."""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.budget import ELASTICITY, compute_financial_profile
from app.core.llm_service import call_llm
from app.core.transaction_semantics import spending_clause, verified_income_clause
from app.models.goal import Goal
from app.models.recurring_pattern import RecurringPattern
from app.models.subscription import Subscription
from app.models.transaction import Transaction

logger = logging.getLogger(__name__)


def _month_start(y: int, m: int) -> date:
    return date(y, m, 1)


def _prev_month(y: int, m: int, n: int = 1) -> tuple[int, int]:
    """Go back n months from (y, m)."""
    for _ in range(n):
        m -= 1
        if m < 1:
            m = 12
            y -= 1
    return y, m


def build_financial_profile_text(db: Session) -> str:
    """Build a comprehensive text profile of the user's finances for the LLM system prompt."""
    today = date.today()
    cur_y, cur_m = today.year, today.month
    month_start = _month_start(cur_y, cur_m)

    # --- Current month data ---
    income = float(
        db.query(func.coalesce(func.sum(Transaction.amount), 0))
        .filter(
            Transaction.date >= month_start,
            Transaction.status != 'deleted',
            verified_income_clause(Transaction),
        )
        .scalar()
    )

    total_spend = float(
        db.query(func.coalesce(func.sum(Transaction.amount), 0))
        .filter(
            Transaction.date >= month_start,
            Transaction.status != 'deleted',
            spending_clause(Transaction),
        )
        .scalar()
    )

    # Top categories this month
    cat_rows = (
        db.query(Transaction.category, func.sum(Transaction.amount).label('total'))
        .filter(
            Transaction.date >= month_start,
            Transaction.status != 'deleted',
            spending_clause(Transaction),
            Transaction.category.isnot(None),
        )
        .group_by(Transaction.category)
        .order_by(func.sum(Transaction.amount).desc())
        .limit(5)
        .all()
    )
    top_cats = ', '.join(f"{r.category}: Rs {float(r.total):,.0f}" for r in cat_rows)

    # --- Historical data (last 3 months, excluding current) ---
    hist_lines = []
    for i in range(1, 4):
        py, pm = _prev_month(cur_y, cur_m, i)
        ms = _month_start(py, pm)
        me = _month_start(*_prev_month(cur_y, cur_m, i - 1)) if i > 1 else month_start
        # For i==1, me = current month_start (correct)
        # For i==2, me = prev_month(1) start, etc. — recalculate cleanly
        me = _month_start(py + (1 if pm == 12 else 0), (pm % 12) + 1)

        h_income = float(
            db.query(func.coalesce(func.sum(Transaction.amount), 0))
            .filter(Transaction.date >= ms, Transaction.date < me,
                    Transaction.status != 'deleted', verified_income_clause(Transaction))
            .scalar()
        )
        h_spend = float(
            db.query(func.coalesce(func.sum(Transaction.amount), 0))
            .filter(Transaction.date >= ms, Transaction.date < me,
                    Transaction.status != 'deleted', spending_clause(Transaction))
            .scalar()
        )
        h_cats = (
            db.query(Transaction.category, func.sum(Transaction.amount).label('total'))
            .filter(Transaction.date >= ms, Transaction.date < me,
                    Transaction.status != 'deleted', spending_clause(Transaction),
                    Transaction.category.isnot(None))
            .group_by(Transaction.category)
            .order_by(func.sum(Transaction.amount).desc())
            .limit(3)
            .all()
        )
        h_cat_text = ', '.join(f"{r.category}: Rs {float(r.total):,.0f}" for r in h_cats) or 'No data'
        month_label = ms.strftime('%B %Y')
        hist_lines.append(
            f"  {month_label}: Income Rs {h_income:,.0f}, Spend Rs {h_spend:,.0f} | Top: {h_cat_text}"
        )

    history_text = '\n'.join(hist_lines)

    # --- All-time totals ---
    total_txn_count = db.query(func.count(Transaction.id)).filter(
        Transaction.status != 'deleted',
    ).scalar() or 0

    all_time_spend = float(
        db.query(func.coalesce(func.sum(Transaction.amount), 0))
        .filter(Transaction.status != 'deleted', spending_clause(Transaction))
        .scalar()
    )

    earliest_txn = db.query(func.min(Transaction.date)).filter(
        Transaction.status != 'deleted',
    ).scalar()
    data_since = earliest_txn.strftime('%B %Y') if earliest_txn else 'N/A'

    # Financial profile metrics
    profile = compute_financial_profile(db)

    # Goals (only active ones)
    goals = db.query(Goal).filter(Goal.deadline_date >= today, Goal.is_active == True).all()
    goal_progress = [
        min(100.0, max(0.0, float(g.current_saved or 0) / float(g.target_amount) * 100))
        for g in goals
        if g.target_amount and float(g.target_amount) > 0
    ]
    goals_text = (
        f"{len(goals)} active; average progress "
        f"{sum(goal_progress) / len(goal_progress):.0f}%"
        if goal_progress
        else f"{len(goals)} active"
    )

    # Recurring expenses
    recurring_total = float(
        db.query(func.coalesce(func.sum(RecurringPattern.avg_amount), 0))
        .filter(RecurringPattern.is_active == True, RecurringPattern.frequency == 'monthly')
        .scalar()
    )

    # Subscriptions
    sub_total = float(
        db.query(func.coalesce(func.sum(Subscription.amount), 0))
        .filter(
            Subscription.is_active == True,
            Subscription.deleted_at.is_(None),
            Subscription.frequency == 'monthly',
        )
        .scalar()
    )

    savings_rate = (
        f"{profile.savings_rate:.1f}%"
        if profile.savings_rate is not None
        else "Unavailable (not enough verified income in the complete month)"
    )

    return f"""User Financial Profile:

Current Month to Date ({today.strftime('%B %Y')} — incomplete period):
- Income: Rs {income:,.0f}
- Spending: Rs {total_spend:,.0f}
- Top Categories: {top_cats or 'No data yet'}

Latest Complete Month ({profile.period_start} to {profile.period_end}):
- Amount kept from income: {savings_rate}
- Small flexible purchase share: {profile.impulse_index if profile.impulse_index is not None else 'Unavailable'}
- Fixed-cost share of income: {profile.fixed_expense_ratio if profile.fixed_expense_ratio is not None else 'Unavailable'}
- Calculation status: {profile.data_status}

Last 3 Months:
{history_text}

Overall:
- Data since: {data_since}
- Total transactions tracked: {total_txn_count:,}
- All-time spending: Rs {all_time_spend:,.0f}
- Active Goals: {goals_text}
- Monthly Recurring: Rs {recurring_total:,.0f}
- Monthly Subscriptions: Rs {sub_total:,.0f}
- Financial ratios above use complete calendar months only."""


SYSTEM_PROMPT = """You are a friendly, knowledgeable personal financial advisor for an Indian user who tracks their finances through GODFIN.

Your role:
- Provide personalized, actionable financial advice based on the user's actual spending data
- Be conversational but concise (2-4 sentences per response unless asked for detail)
- Use Indian Rupees (Rs) for all amounts
- Reference specific categories and amounts from their profile when relevant
- Suggest practical steps, not generic advice
- If asked about investments, provide general guidance only and recommend consulting a SEBI-registered advisor
- Never reveal the raw profile data — just use it to inform your advice naturally

{profile}
"""


def chat(db: Session, user_message: str, conversation_history: list) -> Optional[str]:
    """Handle a chat message. Returns AI response or None if LLM unavailable.

    conversation_history: list of {"role": "user"|"assistant", "content": str}
    """
    profile_text = build_financial_profile_text(db)
    system = SYSTEM_PROMPT.format(profile=profile_text)

    # Build the full prompt with conversation context
    prompt_parts = [f"System: {system}\n"]

    for msg in conversation_history[-4:]:
        role = msg.get('role', 'user')
        content = msg.get('content', '')
        prompt_parts.append(f"{role.capitalize()}: {content}")

    prompt_parts.append(f"User: {user_message}")
    prompt_parts.append("Assistant:")

    full_prompt = '\n'.join(prompt_parts)

    response = call_llm(full_prompt, temperature=0.5, purpose="advisor")
    if not response:
        return None

    return response.strip()
