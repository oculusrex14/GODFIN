from __future__ import annotations

import io
import json
import logging
import re
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from fpdf import FPDF
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.budget import ELASTICITY
from app.core.llm_service import call_llm, estimate_tokens
from app.core.money import money_decimal
from app.core.transaction_semantics import spending_clause, verified_income_clause
from app.models.app_setting import AppSetting
from app.models.recurring_pattern import RecurringPattern
from app.models.transaction import Transaction

logger = logging.getLogger(__name__)

CHART_DPI = 300
REPORT_CALCULATION_VERSION = "2.0"
REPORT_SAVINGS_TARGET_KEY = "report_savings_target_percent"
DEFAULT_SAVINGS_TARGET_PERCENT = Decimal("20.0")
MIN_SAVINGS_TARGET_PERCENT = Decimal("1.0")
MAX_SAVINGS_TARGET_PERCENT = Decimal("80.0")
_PERCENT_QUANTUM = Decimal("0.1")


class DetailedReportUnavailable(RuntimeError):
    """Raised when a requested AI-authored report cannot be produced honestly."""


CHART_COLORS = [
    '#34d399', '#60a5fa', '#f472b6', '#fbbf24',
    '#a78bfa', '#fb923c', '#2dd4bf', '#f87171',
    '#818cf8', '#4ade80', '#e879f9', '#38bdf8',
]


def _get_pyplot():
    """Load Matplotlib only when a PDF/chart is requested."""
    import matplotlib

    matplotlib.use('Agg')
    import matplotlib.pyplot as pyplot

    return pyplot


def _month_range(month: str):
    """Return (start_date, end_date) for a YYYY-MM month string."""
    year, mon = int(month[:4]), int(month[5:7])
    start = date(year, mon, 1)
    if mon == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, mon + 1, 1)
    return start, end


def _percent(value: Decimal) -> float:
    return float(value.quantize(_PERCENT_QUANTUM, rounding=ROUND_HALF_UP))


def _month_status(month: str, *, as_of: date) -> str:
    start, end = _month_range(month)
    if start > as_of:
        return "future"
    if end <= as_of:
        return "complete"
    return "partial"


def get_savings_target_percent(db: Session) -> Decimal:
    setting = db.query(AppSetting).filter_by(key=REPORT_SAVINGS_TARGET_KEY).first()
    try:
        target = Decimal(str(setting.value)) if setting else DEFAULT_SAVINGS_TARGET_PERCENT
    except (TypeError, ValueError, ArithmeticError):
        target = DEFAULT_SAVINGS_TARGET_PERCENT
    if not target.is_finite() or not (
        MIN_SAVINGS_TARGET_PERCENT <= target <= MAX_SAVINGS_TARGET_PERCENT
    ):
        target = DEFAULT_SAVINGS_TARGET_PERCENT
    return target.quantize(_PERCENT_QUANTUM, rounding=ROUND_HALF_UP)


def set_savings_target_percent(db: Session, value: Decimal | float | str) -> Decimal:
    try:
        target = Decimal(str(value)).quantize(
            _PERCENT_QUANTUM,
            rounding=ROUND_HALF_UP,
        )
    except (TypeError, ValueError, ArithmeticError) as exc:
        raise ValueError("Savings target must be a finite percentage") from exc
    if not target.is_finite() or not (
        MIN_SAVINGS_TARGET_PERCENT <= target <= MAX_SAVINGS_TARGET_PERCENT
    ):
        raise ValueError("Savings target must be between 1% and 80%")
    setting = db.query(AppSetting).filter_by(key=REPORT_SAVINGS_TARGET_KEY).first()
    if setting is None:
        setting = AppSetting(key=REPORT_SAVINGS_TARGET_KEY, value=str(target))
        db.add(setting)
    else:
        setting.value = str(target)
    db.commit()
    return target


def _monthly_recurring_amount(pattern: RecurringPattern) -> Decimal:
    amount = money_decimal(pattern.avg_amount)
    divisor = {
        "monthly": Decimal("1"),
        "quarterly": Decimal("3"),
        "annual": Decimal("12"),
    }.get(pattern.frequency)
    if divisor is None:
        return Decimal("0.00")
    return (amount / divisor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# --- Data Preparation ---

def prepare_summary_report(
    db: Session,
    month: str,
    *,
    as_of: date | None = None,
) -> dict:
    start, end = _month_range(month)
    reference_day = as_of or date.today()
    period_status = _month_status(month, as_of=reference_day)
    target_percent = get_savings_target_percent(db)

    base = db.query(Transaction).filter(
        Transaction.date >= start,
        Transaction.date < end,
        Transaction.status != 'deleted',
    )

    total_spend = money_decimal(
        base.filter(spending_clause(Transaction))
        .with_entities(func.coalesce(func.sum(Transaction.amount), 0))
        .scalar()
    )

    total_income = money_decimal(
        base.filter(verified_income_clause(Transaction))
        .with_entities(func.coalesce(func.sum(Transaction.amount), 0))
        .scalar()
    )

    savings_rate = None
    if total_income > 0:
        savings_rate = _percent(
            ((total_income - total_spend) / total_income) * Decimal("100")
        )

    transaction_count = base.filter(
        spending_clause(Transaction)
    ).count()

    avg_transaction = (
        (total_spend / transaction_count).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
        if transaction_count > 0
        else Decimal("0.00")
    )

    # Category breakdown
    category_rows = (
        base.filter(
            spending_clause(Transaction),
            Transaction.category.isnot(None),
        )
        .with_entities(Transaction.category, func.sum(Transaction.amount).label('total'))
        .group_by(Transaction.category)
        .order_by(func.sum(Transaction.amount).desc())
        .all()
    )
    category_amounts = [
        (row.category, money_decimal(row.total))
        for row in category_rows
    ]
    categories = [
        {'category': category, 'amount': float(amount)}
        for category, amount in category_amounts
    ]

    # Elasticity breakdown
    elasticity_amounts = {
        'fixed': Decimal("0.00"),
        'semi_flexible': Decimal("0.00"),
        'flexible': Decimal("0.00"),
    }
    for category, amount in category_amounts:
        elast = ELASTICITY.get(category, 'flexible')
        if elast in elasticity_amounts:
            elasticity_amounts[elast] += amount
    elasticity = {
        key: float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        for key, value in elasticity_amounts.items()
    }

    # Every active cadence is converted to one monthly equivalent. A quarterly
    # or annual commitment must not disappear from the monthly money picture.
    recurring_patterns = (
        db.query(RecurringPattern)
        .filter(RecurringPattern.is_active == True)
        .all()
    )
    recurring_total = sum(
        (_monthly_recurring_amount(pattern) for pattern in recurring_patterns),
        Decimal("0.00"),
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    target_fraction = target_percent / Decimal("100")
    required_reduction = Decimal("0.00")
    flexible_reduction = Decimal("0.00")
    remaining_gap = Decimal("0.00")
    assessment_available = period_status == "complete" and total_income > 0
    if assessment_available:
        required_reduction = max(
            Decimal("0.00"),
            total_spend - ((Decimal("1") - target_fraction) * total_income),
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        flexible_reduction = min(
            required_reduction,
            elasticity_amounts['flexible'],
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        remaining_gap = (required_reduction - flexible_reduction).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

    # Compatibility fields now expose a single, reproducible target-attainment
    # calculation rather than an unvalidated composite "health" judgement.
    financial_health_score = None
    financial_health_label = "Complete the month to compare with your target"
    health_components = {}
    if period_status == "future":
        financial_health_label = "This month has not started"
    elif period_status == "complete" and total_income <= 0:
        financial_health_label = "Add verified income to compare with your target"
    elif assessment_available:
        savings_decimal = Decimal(str(savings_rate))
        progress = max(
            Decimal("0"),
            min(Decimal("100"), savings_decimal / target_percent * Decimal("100")),
        )
        financial_health_score = int(
            progress.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
        if required_reduction == 0:
            financial_health_label = "Monthly savings target reached"
        elif total_spend > total_income:
            financial_health_label = "Spending was higher than recorded income"
        else:
            financial_health_label = "Monthly savings target not yet reached"
        health_components = {
            "savings_target_progress_percent": financial_health_score,
            "recorded_savings_rate_percent": savings_rate,
            "target_savings_rate_percent": float(target_percent),
        }

    if period_status == "partial":
        health_caveat = (
            "This month is still open, so GODFIN shows current totals but waits "
            "until month-end before scoring target progress or suggesting a cut."
        )
    elif period_status == "future":
        health_caveat = "No assessment is available for a future month."
    elif total_income <= 0:
        health_caveat = (
            "A savings target needs verified recorded income. No score or spending "
            "recommendation is produced without it."
        )
    else:
        health_caveat = (
            f"Version {REPORT_CALCULATION_VERSION}: target progress equals the "
            "recorded savings rate divided by your monthly target, capped at 100. "
            "It is not a credit score or a financial diagnosis."
        )

    return {
        'month': month,
        'period_status': period_status,
        'period_start': start.isoformat(),
        'period_end_exclusive': end.isoformat(),
        'as_of_date': reference_day.isoformat(),
        'calculation_version': REPORT_CALCULATION_VERSION,
        'total_spend': float(total_spend),
        'total_income': float(total_income),
        'savings_rate': savings_rate,
        'transaction_count': transaction_count,
        'avg_transaction': float(avg_transaction),
        'top_categories': categories[:5],
        'all_categories': categories,
        'spending_by_elasticity': elasticity,
        'recurring_total': float(recurring_total),
        'savings_target_percent': float(target_percent),
        'savings_target_assessment_available': assessment_available,
        'target_already_met': assessment_available and required_reduction == 0,
        'required_spend_reduction_to_target': (
            float(required_reduction) if assessment_available else None
        ),
        'actionable_flexible_reduction': (
            float(flexible_reduction) if assessment_available else None
        ),
        'remaining_target_gap': (
            float(remaining_gap) if assessment_available else None
        ),
        'financial_health_score': financial_health_score,
        'financial_health_label': financial_health_label,
        'financial_health_components': health_components,
        'financial_health_version': REPORT_CALCULATION_VERSION,
        'financial_health_formula': (
            "clamp(max(0, recorded_savings_rate) / target_savings_rate * 100, 0, 100)"
        ),
        'financial_health_caveat': health_caveat,
    }


def prepare_detailed_report(
    db: Session,
    month: str,
    *,
    as_of: date | None = None,
) -> dict:
    summary = prepare_summary_report(db, month, as_of=as_of)
    start, end = _month_range(month)

    base = db.query(Transaction).filter(
        Transaction.date >= start,
        Transaction.date < end,
        Transaction.status != 'deleted',
    )

    # Top merchants by spend
    merchant_rows = (
        base.filter(
            spending_clause(Transaction),
        )
        .with_entities(
            Transaction.merchant_normalized,
            func.sum(Transaction.amount).label('total'),
            func.count(Transaction.id).label('count'),
        )
        .group_by(Transaction.merchant_normalized)
        .order_by(func.sum(Transaction.amount).desc())
        .limit(10)
        .all()
    )
    top_merchants = [
        {'merchant': r.merchant_normalized, 'amount': round(float(r.total), 2), 'count': r.count}
        for r in merchant_rows
    ]

    # Daily spending timeline
    daily_rows = (
        base.filter(
            spending_clause(Transaction),
        )
        .with_entities(
            Transaction.date,
            func.sum(Transaction.amount).label('total'),
        )
        .group_by(Transaction.date)
        .order_by(Transaction.date)
        .all()
    )
    daily_spending = [
        {'date': str(r.date), 'amount': round(float(r.total), 2)}
        for r in daily_rows
    ]

    # Category comparison uses up to three prior calendar months relative to the
    # selected report month. The denominator is the number of months that actually
    # contain spending evidence, so sparse history is never silently treated as zero.
    y, m = int(month[:4]), int(month[5:7])
    comparison_months: list[tuple[int, int]] = []
    for back in range(1, 4):
        pm, py = m - back, y
        while pm <= 0:
            pm += 12
            py -= 1
        comparison_months.append((py, pm))

    comp_start_y, comp_start_m = comparison_months[-1]
    three_months_ago = date(comp_start_y, comp_start_m, 1)

    avg_rows = (
        db.query(
            Transaction.category,
            func.sum(Transaction.amount).label('total'),
        )
        .filter(
            Transaction.date >= three_months_ago,
            Transaction.date < start,
            Transaction.status != 'deleted',
            spending_clause(Transaction),
            Transaction.category.isnot(None),
        )
        .group_by(Transaction.category)
        .all()
    )

    observed_month_rows = (
        db.query(Transaction.date)
        .filter(
            Transaction.date >= three_months_ago,
            Transaction.date < start,
            Transaction.status != 'deleted',
            spending_clause(Transaction),
        )
        .all()
    )
    observed_months = sorted(
        {f"{row.date.year}-{row.date.month:02d}" for row in observed_month_rows}
    )
    months_in_period = len(observed_months)
    category_comparison = []
    if summary['period_status'] == 'complete' and months_in_period > 0:
        avg_by_cat = {
            row.category: float(
                (money_decimal(row.total) / months_in_period).quantize(
                    Decimal("0.01"),
                    rounding=ROUND_HALF_UP,
                )
            )
            for row in avg_rows
        }
        for cat_row in summary['all_categories']:
            cat = cat_row['category']
            category_comparison.append({
                'category': cat,
                'current': cat_row['amount'],
                'average': avg_by_cat.get(cat, 0.0),
                'sample_months': months_in_period,
            })

    # Recurring patterns
    patterns = (
        db.query(RecurringPattern)
        .filter(RecurringPattern.is_active == True)
        .all()
    )
    recurring_list = [
        {
            'merchant': p.merchant_normalized,
            'amount': float(money_decimal(p.avg_amount)),
            'monthly_equivalent': float(_monthly_recurring_amount(p)),
            'frequency': p.frequency,
            'category': p.category,
        }
        for p in patterns
    ]

    income_rows = (
        base.filter(verified_income_clause(Transaction))
        .with_entities(
            Transaction.subcategory,
            Transaction.merchant_normalized,
            func.sum(Transaction.amount).label("total"),
        )
        .group_by(Transaction.subcategory, Transaction.merchant_normalized)
        .order_by(func.sum(Transaction.amount).desc())
        .all()
    )
    income_breakdown = [
        {
            "source": row.subcategory or row.merchant_normalized or "Other income",
            "amount": round(float(row.total), 2),
        }
        for row in income_rows
    ]

    return {
        **summary,
        'top_merchants': top_merchants,
        'daily_spending': daily_spending,
        'category_comparison': category_comparison,
        'category_comparison_sample_size': (
            months_in_period if summary['period_status'] == 'complete' else 0
        ),
        'category_comparison_months': (
            observed_months if summary['period_status'] == 'complete' else []
        ),
        'category_comparison_caveat': (
            f"Average of {months_in_period} prior recorded complete month(s). "
            "Months with spending in other categories count as zero for an absent category."
            if summary['period_status'] == 'complete' and months_in_period > 0
            else (
                "Current partial months are not compared with complete historical months."
                if summary['period_status'] == 'partial'
                else "No prior recorded complete month is available for comparison."
            )
        ),
        'recurring_list': recurring_list,
        'income_breakdown': income_breakdown,
    }


# --- Spending Trend (reuse dashboard logic) ---

def _get_spending_trend(
    db: Session,
    month: str,
    num_months: int = 6,
    *,
    as_of: date | None = None,
) -> list:
    reference_day = as_of or date.today()
    report_start, report_end = _month_range(month)
    if report_end <= reference_day:
        anchor = report_start
    else:
        current_start = date(reference_day.year, reference_day.month, 1)
        anchor = (
            date(current_start.year - 1, 12, 1)
            if current_start.month == 1
            else date(current_start.year, current_start.month - 1, 1)
        )
    year, mon = anchor.year, anchor.month
    result = []

    for i in range(num_months - 1, -1, -1):
        m = mon - i
        y = year
        while m <= 0:
            m += 12
            y -= 1

        m_start = date(y, m, 1)
        m_end = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)

        spend = money_decimal(
            db.query(func.coalesce(func.sum(Transaction.amount), 0))
            .filter(
                Transaction.date >= m_start,
                Transaction.date < m_end,
                Transaction.status != 'deleted',
                spending_clause(Transaction),
            )
            .scalar()
        )
        income = money_decimal(
            db.query(func.coalesce(func.sum(Transaction.amount), 0))
            .filter(
                Transaction.date >= m_start,
                Transaction.date < m_end,
                Transaction.status != 'deleted',
                verified_income_clause(Transaction),
            )
            .scalar()
        )
        transaction_count = (
            db.query(Transaction.id)
            .filter(
                Transaction.date >= m_start,
                Transaction.date < m_end,
                Transaction.status != 'deleted',
                (spending_clause(Transaction) | verified_income_clause(Transaction)),
            )
            .count()
        )
        result.append({
            'month': f'{y}-{m:02d}',
            'label': m_start.strftime('%b %Y'),
            'spend': float(spend),
            'income': float(income),
            'transaction_count': transaction_count,
            'has_observed_data': transaction_count > 0,
            'period_status': 'complete',
        })

    return result


# --- Chart Generation ---

def generate_category_chart(category_data: list) -> bytes:
    """Generate a pie chart PNG from category breakdown data."""
    plt = _get_pyplot()
    if not category_data:
        return _empty_chart('No spending data', plt)

    fig, ax = plt.subplots(figsize=(5, 4), facecolor='#1a1f36')
    ax.set_facecolor('#1a1f36')

    labels = [d['category'] for d in category_data[:8]]
    values = [d['amount'] for d in category_data[:8]]
    colors = CHART_COLORS[:len(labels)]

    wedges, texts, autotexts = ax.pie(
        values, labels=None, colors=colors, autopct='%1.0f%%',
        startangle=90, pctdistance=0.8,
        wedgeprops=dict(width=0.5, edgecolor='#1a1f36', linewidth=1.5),
    )

    for t in autotexts:
        t.set_color('white')
        t.set_fontsize(8)

    ax.legend(
        labels, loc='center left', bbox_to_anchor=(1, 0.5),
        fontsize=8, frameon=False, labelcolor='white',
    )

    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=CHART_DPI, bbox_inches='tight',
                facecolor='#1a1f36', edgecolor='none')
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


def generate_trend_chart(trend_data: list) -> bytes:
    """Generate a spending trend line chart PNG."""
    plt = _get_pyplot()
    if not trend_data:
        return _empty_chart('No trend data', plt)

    fig, ax = plt.subplots(figsize=(6, 3), facecolor='#1a1f36')
    ax.set_facecolor('#1a1f36')

    labels = [d['label'] for d in trend_data]
    spend = [d['spend'] for d in trend_data]
    income = [d['income'] for d in trend_data]

    ax.plot(labels, spend, color='#f87171', marker='o', markersize=4, linewidth=2, label='Spend')
    ax.plot(labels, income, color='#34d399', marker='o', markersize=4, linewidth=2, label='Income')

    ax.tick_params(colors='#94a3b8', labelsize=8)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['bottom'].set_color('#334155')
    ax.spines['left'].set_color('#334155')
    ax.legend(fontsize=8, frameon=False, labelcolor='white')
    ax.grid(axis='y', color='#334155', linewidth=0.5, alpha=0.5)

    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=CHART_DPI, bbox_inches='tight',
                facecolor='#1a1f36', edgecolor='none')
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


def generate_daily_chart(daily_data: list) -> bytes:
    """Generate a daily spending bar chart PNG."""
    plt = _get_pyplot()
    if not daily_data:
        return _empty_chart('No daily data', plt)

    fig, ax = plt.subplots(figsize=(6, 3), facecolor='#1a1f36')
    ax.set_facecolor('#1a1f36')

    days = [d['date'][-2:] for d in daily_data]
    amounts = [d['amount'] for d in daily_data]

    ax.bar(days, amounts, color='#60a5fa', width=0.6)

    ax.tick_params(colors='#94a3b8', labelsize=7)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['bottom'].set_color('#334155')
    ax.spines['left'].set_color('#334155')
    ax.grid(axis='y', color='#334155', linewidth=0.5, alpha=0.5)

    if len(days) > 15:
        ax.set_xticks(range(0, len(days), 3))

    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=CHART_DPI, bbox_inches='tight',
                facecolor='#1a1f36', edgecolor='none')
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


def _empty_chart(message: str, plt=None) -> bytes:
    if plt is None:
        plt = _get_pyplot()
    fig, ax = plt.subplots(figsize=(4, 3), facecolor='#1a1f36')
    ax.set_facecolor('#1a1f36')
    ax.text(0.5, 0.5, message, ha='center', va='center', color='#64748b', fontsize=12)
    ax.axis('off')
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=CHART_DPI, bbox_inches='tight',
                facecolor='#1a1f36', edgecolor='none')
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


# --- Financial Insights (structured professional report) ---

# Insight schema (returned by deterministic and explicitly requested AI reports):
# {
#   "available": bool,            # whether an LLM-authored report was produced
#   "source": "llm" | "heuristic",
#   "executive_summary": str,     # markdown, 2-4 sentences
#   "sections": [                 # ordered analytical sections
#     {"title": str, "tone": "positive|warning|negative|neutral", "icon": str, "content": str (markdown)}
#   ],
#   "highlights": [               # numeric KPI callouts
#     {"label": str, "value": str, "tone": str, "delta": str|None}
#   ],
#   "recommendations": [str],     # markdown bullet strings
# }

INSIGHT_TONES = ('positive', 'warning', 'negative', 'neutral')


def _tone_for_savings(
    savings_rate,
    target_percent=DEFAULT_SAVINGS_TARGET_PERCENT,
    *,
    assessment_available=True,
):
    if savings_rate is None or not assessment_available:
        return 'neutral'
    if Decimal(str(savings_rate)) >= Decimal(str(target_percent)):
        return 'positive'
    if savings_rate >= 0:
        return 'warning'
    return 'negative'


def _pct(part: float, whole: float) -> float:
    return round((part / whole) * 100, 1) if whole > 0 else 0.0


def _build_insights_prompt(detailed: dict, trend: list, month_label: str) -> str:
    s = detailed
    elastic = s.get('spending_by_elasticity', {})
    top_cats = s.get('top_categories', [])
    target_percent = s.get('savings_target_percent', 20.0)
    assessment_available = bool(s.get('savings_target_assessment_available'))
    history_sample = s.get('category_comparison_sample_size', 0)
    observed_trend = [item for item in trend if item.get('has_observed_data')]

    def amount_or_na(value):
        return "N/A" if value is None else f"Rs {_format_inr(value)}"

    cats_lines = '\n'.join(
        f"  - {c['category']}: Rs {_format_inr(c['amount'])} ({_pct(c['amount'], s['total_spend'])}% of spend)"
        for c in top_cats
    ) or '  - (none)'

    comp_lines = '\n'.join(
        f"  - {c['category']}: report month Rs {_format_inr(c['current'])} vs "
        f"{history_sample}-recorded-month avg Rs {_format_inr(c['average'])}"
        f" (delta {('+' if c['current'] - c['average'] >= 0 else '')}Rs {_format_inr(c['current'] - c['average'])})"
        for c in s.get('category_comparison', [])[:8]
    ) or f"  - unavailable: {s.get('category_comparison_caveat', 'not enough comparable history')}"

    recur_lines = '\n'.join(
        f"  - {r['category']}: Rs {_format_inr(r['amount'])} / {r['frequency']}"
        for r in s.get('recurring_list', [])[:8]
    ) or '  - (none)'

    trend_lines = '\n'.join(
        f"  - {t['month']}: spend Rs {_format_inr(t['spend'])}, income Rs {_format_inr(t['income'])}"
        for t in trend if t.get('has_observed_data')
    ) or '  - (none)'

    return f"""You are writing a careful, plain-language monthly money report for an Indian
user. All amounts are in Indian Rupees (Rs). The report month is {month_label}.

Use ONLY the data below. Do not invent figures. Be specific and actionable using the supplied amount
bands, ratios, and category names. Explain finance terms in everyday language. Do not
diagnose the user, shame spending, or claim certainty that the data cannot support.

=== FINANCIAL DATA ===
Calculation version: {s.get('calculation_version', REPORT_CALCULATION_VERSION)}
Report period status: {s.get('period_status', 'unknown')}
Total Spend: Rs {_format_inr(s.get('total_spend', 0))}
Total Income: Rs {_format_inr(s.get('total_income', 0))}
Savings Rate: {s.get('savings_rate', 'N/A')}%
User's monthly savings target: {target_percent}%
Target assessment available: {assessment_available}
Required spend reduction to reach target: {amount_or_na(s.get('required_spend_reduction_to_target'))}
Reduction available from identified flexible spend: {amount_or_na(s.get('actionable_flexible_reduction'))}
Target gap remaining after identified flexible spend: {amount_or_na(s.get('remaining_target_gap'))}
Transactions: {s.get('transaction_count', 0)}
Average Transaction: Rs {_format_inr(s.get('avg_transaction', 0))}

Spending by elasticity:
  - Fixed: Rs {_format_inr(elastic.get('fixed', 0))}
  - Semi-Flexible: Rs {_format_inr(elastic.get('semi_flexible', 0))}
  - Flexible: Rs {_format_inr(elastic.get('flexible', 0))}
Recurring monthly total: Rs {_format_inr(s.get('recurring_total', 0))}

Top categories:
{cats_lines}

Category comparison ({history_sample} prior recorded complete month(s)):
{comp_lines}

Recurring commitments by category:
{recur_lines}

Finished-month trend ({len(observed_trend)} recorded month(s), oldest → newest; partial months excluded):
{trend_lines}
=== END DATA ===

Respond with ONLY a JSON object (no prose, no markdown fences) in EXACTLY this shape:
{{
  "executive_summary": "2-4 sentence markdown overview of the month's financial position.",
  "sections": [
    {{"title": "Spending Breakdown", "tone": "neutral", "icon": "pie", "content": "markdown: where the money went, top categories with Rs and %, what stands out"}},
    {{"title": "Savings Target Check", "tone": "<positive|warning|negative|neutral>", "icon": "piggy", "content": "markdown: use only the user's target and the supplied solved target-gap fields; explain when the assessment is unavailable"}},
    {{"title": "Finished-Month Trend", "tone": "neutral", "icon": "trend", "content": "markdown: compare only the supplied completed recorded months and state the sample size"}},
    {{"title": "Worth Reviewing", "tone": "<positive|warning|negative|neutral>", "icon": "alert", "content": "markdown: categories above their observed-month average, flexible spend limits, and recurring commitments, with caveats"}}
  ],
  "highlights": [
    {{"label": "Biggest Category", "value": "amount band (Y%)", "tone": "neutral", "delta": null}},
    {{"label": "Flexible Spend", "value": "amount band (Y%)", "tone": "warning", "delta": null}},
    {{"label": "Top Spike vs Avg", "value": "Category amount band", "tone": "negative", "delta": null}}
  ],
  "recommendations": [
    "markdown bullet: one specific, prioritized action using an amount band or percentage target",
    "markdown bullet: a second concrete action",
    "markdown bullet: a third forward-looking action for next month"
  ]
}}

Rules:
- "tone" must be one of: positive, warning, negative, neutral.
- "icon" must be one of: pie, piggy, trend, alert, wallet, repeat.
- Keep executive_summary to 2-4 sentences. Each section's content: 3-6 sentences of markdown (use **bold** for category/amount anchors, and bullet lists where natural).
- 3 recommendations max, each a single bullet string.
- Reference only the supplied bands, percentages, and counts. No generic platitudes.
- Never call the target-progress score a financial-health score, credit score, diagnosis, or prediction.
- If Target assessment available is false, do not judge target performance or recommend a target-closing cut.
- Never compare a partial report month with a completed month.
- If a target gap remains after all identified flexible spend, say clearly that flexible cuts alone cannot reach the target.
- Do not invent a 20%, 25%, or other heuristic cut. Use only the supplied solved reduction fields."""


def _parse_insights_json(raw: str) -> Optional[dict]:
    """Parse the LLM JSON response, tolerating code fences / leading prose."""
    if not raw:
        return None
    import re
    text = raw.strip()
    # Strip markdown code fences if present
    fence = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        # Grab the outermost {...} block
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1 and end > start:
            text = text[start:end + 1]
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    if not isinstance(data.get('executive_summary'), str):
        return None
    sections = data.get('sections')
    if not isinstance(sections, list) or not sections:
        return None
    normalized_sections = []
    for sec in sections[:8]:
        if not isinstance(sec, dict):
            return None
        title = sec.get('title')
        content = sec.get('content')
        if not isinstance(title, str) or not isinstance(content, str):
            return None
        normalized_sections.append({
            'title': title.strip()[:120] or 'Insights',
            'content': content.strip()[:8000],
            'tone': sec.get('tone') if sec.get('tone') in INSIGHT_TONES else 'neutral',
            'icon': sec.get('icon') if sec.get('icon') in {
                'pie', 'piggy', 'trend', 'alert', 'wallet', 'repeat'
            } else 'wallet',
        })

    highlights = data.get('highlights', [])
    if not isinstance(highlights, list):
        return None
    normalized_highlights = []
    for item in highlights[:8]:
        if not isinstance(item, dict):
            return None
        label = item.get('label')
        value = item.get('value')
        if not isinstance(label, str) or not isinstance(value, str):
            return None
        delta = item.get('delta')
        normalized_highlights.append({
            'label': label.strip()[:120],
            'value': value.strip()[:240],
            'tone': item.get('tone') if item.get('tone') in INSIGHT_TONES else 'neutral',
            'delta': delta.strip()[:240] if isinstance(delta, str) else None,
        })

    recommendations = data.get('recommendations', [])
    if not isinstance(recommendations, list) or any(
        not isinstance(item, str) for item in recommendations
    ):
        return None
    data = {
        'executive_summary': data['executive_summary'].strip()[:8000],
        'sections': normalized_sections,
        'highlights': normalized_highlights,
        'recommendations': [item.strip()[:2000] for item in recommendations[:3]],
    }
    return data


def _heuristic_insights(detailed: dict, trend: list) -> dict:
    """Build plain-language notes from versioned, completed-period calculations."""
    s = detailed
    spend = s.get('total_spend', 0)
    income = s.get('total_income', 0)
    savings = s.get('savings_rate')
    target = s.get('savings_target_percent', 20.0)
    assessment_available = bool(s.get('savings_target_assessment_available'))
    period_status = s.get('period_status', 'unknown')
    required_reduction = s.get('required_spend_reduction_to_target')
    actionable_reduction = s.get('actionable_flexible_reduction')
    remaining_gap = s.get('remaining_target_gap')
    elastic = s.get('spending_by_elasticity', {})
    fixed = elastic.get('fixed', 0)
    flex = elastic.get('flexible', 0)
    top = s.get('top_categories', [])
    comp = s.get('category_comparison', [])
    comparison_sample = s.get('category_comparison_sample_size', 0)
    recurring = s.get('recurring_total', 0)

    # Executive summary
    if spend == 0 and income == 0:
        exec_sum = "No transactions were recorded for this period, so there is nothing to analyse yet. " \
                   "Once alerts are ingested, this report will populate automatically."
    elif period_status == 'partial':
        exec_sum = f"These are **current-to-date totals for {month_label_of(s)}**: Rs " \
                   f"{_format_inr(spend)} spent and Rs {_format_inr(income)} of verified income recorded. " \
                   "Because the month is still open, GODFIN does not score target progress or compare it " \
                   "with complete months yet."
    elif assessment_available and required_reduction == 0:
        exec_sum = f"In **{month_label_of(s)}** you kept **{savings:.1f}%** of recorded income, meeting " \
                   f"your {target:.1f}% monthly target. Spending was Rs {_format_inr(spend)} across " \
                   f"{s.get('transaction_count', 0)} transactions."
    elif assessment_available:
        exec_sum = f"In **{month_label_of(s)}** you spent Rs {_format_inr(spend)} against verified " \
                   f"income of Rs {_format_inr(income)}, keeping **{savings:.1f}%**. Reaching your " \
                   f"{target:.1f}% target would have required Rs {_format_inr(required_reduction or 0)} " \
                   "less spending with income unchanged."
    else:
        exec_sum = f"You recorded Rs {_format_inr(spend)} of spending across " \
                   f"{s.get('transaction_count', 0)} transactions in **{month_label_of(s)}**. " \
                   "Verified income is needed before GODFIN can compare this month with your savings target."

    # Spending Breakdown section
    if top:
        top_lines = [f"**{c['category']}** led spending at Rs {_format_inr(c['amount'])} "
                     f"({_pct(c['amount'], spend)}% of total)." for c in top[:3]]
        breakdown = ' '.join(top_lines)
        breakdown += f" Fixed commitments accounted for Rs {_format_inr(fixed)} ({_pct(fixed, spend)}%), " \
                     f"while flexible spend was Rs {_format_inr(flex)} ({_pct(flex, spend)}%)."
    else:
        breakdown = "No categorised spending was recorded for this period."
    sections = [{
        'title': 'Spending Breakdown',
        'tone': 'neutral',
        'icon': 'pie',
        'content': breakdown,
    }]

    # Savings target section: only a completed month with verified income can
    # produce an assessment or an amount recommendation.
    tone_s = _tone_for_savings(
        savings,
        target,
        assessment_available=assessment_available,
    )
    if period_status == 'partial':
        target_note = (
            "The month is still open. Current totals are useful for checking transactions, but "
            "a target result or suggested cut now would compare an unfinished period unfairly."
        )
    elif period_status == 'future':
        target_note = "This month has not started, so no target result is available."
    elif not assessment_available:
        target_note = (
            "No verified income was recorded, so GODFIN cannot calculate how much of income was "
            "kept or solve a target gap."
        )
    elif required_reduction == 0:
        target_note = f"You kept **{savings:.1f}%** of recorded income and met your **{target:.1f}%** " \
                      "monthly target. The result describes this completed month only."
    elif (remaining_gap or 0) == 0:
        target_note = f"The exact gap to your **{target:.1f}%** target was Rs " \
                      f"{_format_inr(required_reduction)}. Identified flexible spending could cover " \
                      "that amount if income and all other spending stayed unchanged."
    else:
        target_note = f"The exact gap to your **{target:.1f}%** target was Rs " \
                      f"{_format_inr(required_reduction or 0)}. The recorded flexible categories " \
                      f"could cover at most Rs {_format_inr(actionable_reduction or 0)}, leaving " \
                      f"Rs {_format_inr(remaining_gap or 0)}. Flexible cuts alone therefore cannot " \
                      "reach the target; do not automatically cut essential costs."
    sections.append({
        'title': 'Savings Target Check',
        'tone': tone_s,
        'icon': 'piggy',
        'content': target_note,
    })

    # Trend section uses recorded, completed months only.
    observed_trend = [
        item for item in trend
        if item.get('has_observed_data', bool(item.get('spend') or item.get('income')))
    ]
    if len(observed_trend) >= 2:
        cur = observed_trend[-1]
        prev = observed_trend[-2]
        spend_delta = cur['spend'] - prev['spend']
        if spend_delta > 0:
            change_text = f"up Rs {_format_inr(spend_delta)}"
        elif spend_delta < 0:
            change_text = f"down Rs {_format_inr(abs(spend_delta))}"
        else:
            change_text = "unchanged"
        avg6 = sum(t['spend'] for t in observed_trend) / len(observed_trend)
        vs_avg = cur['spend'] - avg6
        if vs_avg > 0:
            average_text = f"above the {len(observed_trend)}-recorded-month average by Rs {_format_inr(vs_avg)}"
        elif vs_avg < 0:
            average_text = f"below the {len(observed_trend)}-recorded-month average by Rs {_format_inr(abs(vs_avg))}"
        else:
            average_text = f"equal to the {len(observed_trend)}-recorded-month average"
        momentum = (
            f"In {cur['label']}, spending was Rs {_format_inr(cur['spend'])}, {change_text} "
            f"from {prev['label']} (Rs {_format_inr(prev['spend'])}). It was {average_text}. "
            "Only finished calendar months with recorded data are included."
        )
    else:
        momentum = f"Only {len(observed_trend)} recorded finished month(s) are available. At least " \
                   "two are needed for a direction comparison."
    sections.append({
        'title': 'Finished-Month Trend',
        'tone': 'neutral',
        'icon': 'trend',
        'content': momentum,
    })

    # Watch-outs section
    spikes = []
    for c in comp:
        diff = c['current'] - c['average']
        if c['average'] > 0 and diff > 0:
            spikes.append((c['category'], diff, c['current'], c['average']))
    spikes.sort(key=lambda x: x[1], reverse=True)

    watch_lines = []
    if spikes:
        for cat, diff, cur, avg in spikes[:3]:
            pct_inc = round((diff / avg) * 100) if avg > 0 else 0
            watch_lines.append(f"**{cat}** was Rs {_format_inr(diff)} (+{pct_inc}%) above its average "
                               f"across {comparison_sample} prior recorded month(s) "
                               f"(Rs {_format_inr(avg)} to Rs {_format_inr(cur)}).")
    if flex > 0:
        watch_lines.append(f"Flexible categories were Rs {_format_inr(flex)} "
                           f"({_pct(flex, spend)}% of recorded spending).")
    if recurring > 0 and income > 0:
        watch_lines.append(f"Confirmed recurring commitments have a monthly equivalent of Rs "
                           f"{_format_inr(recurring)}, or {_pct(recurring, income)}% of recorded income.")
    if not watch_lines:
        watch_lines.append("There is not enough completed comparison history to identify a category "
                           "that was above its prior recorded-month average.")
    watch_tone = 'warning' if spikes and comparison_sample >= 2 else 'neutral'
    sections.append({
        'title': 'Worth Reviewing',
        'tone': watch_tone,
        'icon': 'alert',
        'content': '\n'.join(f"- {w}" for w in watch_lines),
    })

    # Highlights
    highlights = []
    if top:
        highlights.append({
            'label': 'Biggest Category',
            'value': f"{top[0]['category']} · Rs {_format_inr(top[0]['amount'])}",
            'tone': 'neutral',
            'delta': f"{_pct(top[0]['amount'], spend)}% of spend",
        })
    if flex or fixed:
        highlights.append({
            'label': 'Flexible Spend',
            'value': f"Rs {_format_inr(flex)} ({_pct(flex, spend)}%)",
            'tone': 'warning' if _pct(flex, spend) > 40 else 'neutral',
            'delta': None,
        })
    if spikes:
        cat, diff, cur, avg = spikes[0]
        highlights.append({
            'label': 'Top Spike vs Avg',
            'value': f"{cat} · +Rs {_format_inr(diff)}",
            'tone': 'negative',
            'delta': f"vs Rs {_format_inr(avg)} avg",
        })
    if savings is not None:
        highlights.append({
            'label': 'Recorded Savings Rate',
            'value': f"{savings:.1f}%" if assessment_available else "Current-to-date",
            'tone': tone_s,
            'delta': (
                f"Target {target:.1f}%"
                if assessment_available
                else "Target check waits for month-end"
            ),
        })

    # Recommendations
    recs = []
    if spikes:
        cat, diff, _, _ = spikes[0]
        recs.append(f"**Review {cat} first** — it was Rs {_format_inr(diff)} above its average "
                    f"across {comparison_sample} prior recorded month(s). Check the underlying "
                    "transactions before deciding whether this was exceptional or repeatable.")
    if assessment_available and (required_reduction or 0) > 0:
        if (remaining_gap or 0) == 0 and (actionable_reduction or 0) > 0:
            recs.append(f"**Target the solved gap, not a guessed percentage** — reducing recorded "
                        f"flexible spending by Rs {_format_inr(actionable_reduction)} would have "
                        f"reached the {target:.1f}% target if income and other spending stayed unchanged.")
        elif (actionable_reduction or 0) > 0:
            recs.append(f"**Do not expect flexible cuts alone to reach the target.** The full gap is "
                        f"Rs {_format_inr(required_reduction)}, while identified flexible spending "
                        f"can cover at most Rs {_format_inr(actionable_reduction)}.")
        else:
            recs.append(f"The {target:.1f}% target gap is Rs {_format_inr(required_reduction)}, but "
                        "no recorded category is classified as flexible. Review categories or the target "
                        "instead of cutting essential spending automatically.")
    if recurring > 0:
        recs.append(f"**Review recurring commitments** totalling Rs {_format_inr(recurring)} — cancel "
                    f"unused subscriptions to free up monthly margin.")
    if not recs:
        if assessment_available and required_reduction == 0:
            recs.append(f"Your {target:.1f}% target was met for this completed month. Review another "
                        "finished month before treating it as a lasting pattern.")
        else:
            recs.append("Keep recording income and spending. GODFIN needs a completed month with "
                        "verified income before it can calculate a target result honestly.")

    return {
        'available': True,
        'source': 'heuristic',
        'calculation_version': s.get('calculation_version', REPORT_CALCULATION_VERSION),
        'period_status': period_status,
        'sample_sizes': {
            'category_comparison_months': comparison_sample,
            'trend_recorded_complete_months': len(observed_trend),
        },
        'caveat': s.get('financial_health_caveat'),
        'executive_summary': exec_sum,
        'sections': sections,
        'highlights': highlights,
        'recommendations': recs[:3],
    }


def month_label_of(detailed: dict) -> str:
    m = detailed.get('month')
    if not m:
        return 'this month'
    try:
        return date(int(m[:4]), int(m[5:7]), 1).strftime('%B %Y')
    except Exception:
        return 'this month'


def _empty_insights(detailed: dict) -> dict:
    month_label = month_label_of(detailed)
    return {
        'available': False,
        'source': 'none',
        'calculation_version': detailed.get(
            'calculation_version', REPORT_CALCULATION_VERSION
        ),
        'period_status': detailed.get('period_status', 'unknown'),
        'sample_sizes': {
            'category_comparison_months': detailed.get(
                'category_comparison_sample_size', 0
            ),
            'trend_recorded_complete_months': 0,
        },
        'executive_summary': f"No transactions recorded for {month_label}. Ingest Gmail alerts or "
                             f"upload a statement to populate this report.",
        'sections': [],
        'highlights': [],
        'recommendations': [],
    }


def generate_deterministic_insights(detailed: dict, trend: list) -> dict:
    """Build reproducible commentary without crossing an AI boundary."""
    if detailed.get('total_spend', 0) == 0 and detailed.get('total_income', 0) == 0 \
            and detailed.get('transaction_count', 0) == 0:
        return _empty_insights(detailed)
    return _heuristic_insights(detailed, trend)


def generate_ai_financial_insights(detailed: dict, trend: list) -> dict:
    """Generate an explicitly requested AI report with no heuristic fallback."""
    month_label = month_label_of(detailed)
    if detailed.get('total_spend', 0) == 0 and detailed.get('total_income', 0) == 0 \
            and detailed.get('transaction_count', 0) == 0:
        raise DetailedReportUnavailable(
            f"No recorded activity is available for {month_label}."
        )

    prompt = _build_insights_prompt(detailed, trend, month_label)
    try:
        raw = call_llm(prompt, temperature=0.5, purpose="report")
    except Exception as e:
        logger.warning(f"LLM insights call failed: {e}")
        raw = None

    if raw:
        parsed = _parse_insights_json(raw)
        if parsed:
            parsed['available'] = True
            parsed['source'] = 'llm'
            parsed['calculation_version'] = detailed.get(
                'calculation_version', REPORT_CALCULATION_VERSION
            )
            parsed['period_status'] = detailed.get('period_status', 'unknown')
            parsed['sample_sizes'] = {
                'category_comparison_months': detailed.get(
                    'category_comparison_sample_size', 0
                ),
                'trend_recorded_complete_months': len(
                    [item for item in trend if item.get('has_observed_data')]
                ),
            }
            parsed['caveat'] = detailed.get('financial_health_caveat')
            parsed.setdefault('executive_summary', '')
            return parsed
        logger.warning("LLM insights returned unparseable JSON")

    raise DetailedReportUnavailable(
        "The connected AI did not return a usable report. Check the model "
        "connection and try again; no AI commentary was generated."
    )


# --- PDF Generation ---

def _format_inr(amount: float) -> str:
    """Format amount in INR style."""
    if amount >= 10000000:
        return f'{amount / 10000000:.2f} Cr'
    if amount >= 100000:
        return f'{amount / 100000:.2f} L'
    return f'{amount:,.0f}'


# Characters the built-in latin-1 Helvetica core font cannot render. The LLM
# occasionally emits these even when asked for ASCII, so sanitize any text we
# feed into the PDF to avoid FPDFUnicodeEncodingException.
_UNICODE_REPLACEMENTS = {
    '—': '--',  # em dash
    '–': '-',   # en dash
    '‘': "'",   # left single quote
    '’': "'",   # right single quote
    '“': '"',   # left double quote
    '”': '"',   # right double quote
    '…': '...', # ellipsis
    '₹': 'Rs',  # rupee sign
    ' ': ' ',   # non-breaking space
    '•': '-',   # bullet
    '‐': '-',   # hyphen
    '‑': '-',   # non-breaking hyphen
}


def _sanitize_pdf_text(text) -> str:
    """Map unicode punctuation to ASCII-safe equivalents for the core font."""
    if text is None:
        return ''
    if not isinstance(text, str):
        text = str(text)
    for src, dst in _UNICODE_REPLACEMENTS.items():
        text = text.replace(src, dst)
    # Strip any remaining non-latin-1 characters
    return text.encode('latin-1', 'replace').decode('latin-1')


class ReportPDF(FPDF):
    _is_cover = False
    _suppress_header = False

    # Accent RGB per insight tone
    TONE_COLORS = {
        'positive': (52, 211, 153),   # emerald
        'warning': (251, 191, 36),    # amber
        'negative': (248, 113, 113),  # rose
        'neutral': (148, 163, 184),   # slate
    }

    BG_COLOR = (26, 31, 54)
    BG_ALT = (30, 38, 64)

    def add_page(self, orientation='', format='', same=False):
        # Paint the dark background on every non-cover page BEFORE the header
        # draws, so auto-broken pages stay dark and text remains legible.
        self._suppress_header = True
        super().add_page(orientation, format, same)
        self._suppress_header = False
        if not self._is_cover:
            self.set_fill_color(*self.BG_COLOR)
            self.rect(0, 0, self.w, self.h, 'F')
            self.header()

    def header(self):
        if self._is_cover or getattr(self, '_suppress_header', False):
            return
        self.set_font('Helvetica', 'B', 16)
        self.set_text_color(255, 255, 255)
        self.cell(0, 12, self._report_title, new_x='LMARGIN', new_y='NEXT')
        self.set_font('Helvetica', '', 9)
        self.set_text_color(148, 163, 184)
        self.cell(0, 6, self._report_subtitle, new_x='LMARGIN', new_y='NEXT')
        self.ln(4)

    def footer(self):
        if self._is_cover:
            return
        self.set_y(-15)
        self.set_font('Helvetica', 'I', 7)
        self.set_text_color(100, 116, 139)
        self.cell(0, 10, f'Generated by GODFIN on {datetime.now().strftime("%d %b %Y %H:%M")}',
                  align='C')

    def add_cover_page(self, title: str, subtitle: str, month_label: str):
        self._is_cover = True
        self.add_page()
        self.set_fill_color(*self.BG_COLOR)
        self.rect(0, 0, self.w, self.h, 'F')

        # Centered title area
        self.ln(80)
        self.set_font('Helvetica', 'B', 28)
        self.set_text_color(255, 255, 255)
        self.cell(0, 14, title, align='C', new_x='LMARGIN', new_y='NEXT')
        self.ln(4)
        self.set_font('Helvetica', '', 14)
        self.set_text_color(148, 163, 184)
        self.cell(0, 10, subtitle, align='C', new_x='LMARGIN', new_y='NEXT')
        self.ln(8)
        self.set_font('Helvetica', '', 11)
        self.set_text_color(100, 116, 139)
        self.cell(0, 8, month_label, align='C', new_x='LMARGIN', new_y='NEXT')
        self.ln(4)
        self.cell(0, 8, f'Generated {datetime.now().strftime("%d %b %Y")}', align='C', new_x='LMARGIN', new_y='NEXT')
        self._is_cover = False

    def table_row(self, cells: list, widths: list, row_idx: int = 0, bold: bool = False):
        """Draw a table row with alternating background colors."""
        if row_idx % 2 == 0:
            self.set_fill_color(*self.BG_ALT)
        else:
            self.set_fill_color(*self.BG_COLOR)

        font_style = 'B' if bold else ''
        self.set_font('Helvetica', font_style, 9)

        for i, (cell_text, width) in enumerate(zip(cells, widths)):
            is_last = i == len(cells) - 1
            self.cell(width, 7, str(cell_text), fill=True,
                      new_x='LMARGIN' if is_last else 'END',
                      new_y='NEXT' if is_last else 'TOP')

    # --- Section helpers ---

    def section_label(self, text: str):
        """Small uppercase section label."""
        self.set_font('Helvetica', 'B', 11)
        self.set_text_color(148, 163, 184)
        self.cell(0, 8, text.upper(), new_x='LMARGIN', new_y='NEXT')

    def stat_line(self, label: str, value: str, value_color=(255, 255, 255)):
        self.set_font('Helvetica', '', 10)
        self.set_text_color(148, 163, 184)
        self.cell(70, 7, label)
        self.set_text_color(*value_color)
        self.cell(0, 7, value, new_x='LMARGIN', new_y='NEXT')

    def render_markdown(self, text: str, font_size: int = 9,
                        color=(226, 232, 240), line_height: float = 5.0):
        """Render a lightweight markdown subset: **bold**, bullet lists (- / *),
        ## / ### headings, and paragraphs. Handles wrapping automatically."""
        if not text or not text.strip():
            return
        self.set_text_color(*color)
        blocks = re.split(r'\n\s*\n', text.strip())
        for block in blocks:
            for line in block.split('\n'):
                stripped = _sanitize_pdf_text(line).strip()
                if not stripped:
                    continue
                bm = re.match(r'^[-*]\s+(.*)', stripped)
                if bm:
                    self.set_font('Helvetica', '', font_size)
                    self.set_x(self.l_margin + 4)
                    self.set_text_color(96, 165, 250)  # bullet marker
                    self.cell(4, line_height, '-')
                    self.set_text_color(*color)
                    self.set_x(self.l_margin + 9)
                    self.multi_cell(self.w - self.l_margin - 9 - self.r_margin,
                                    line_height, bm.group(1), markdown=True,
                                    new_x='LMARGIN', new_y='NEXT')
                elif stripped.startswith('### '):
                    self.set_font('Helvetica', 'B', font_size)
                    self.multi_cell(0, line_height + 1, stripped[4:], markdown=True,
                                    new_x='LMARGIN', new_y='NEXT')
                elif stripped.startswith('## '):
                    self.set_font('Helvetica', 'B', font_size + 1)
                    self.multi_cell(0, line_height + 1.2, stripped[3:], markdown=True,
                                    new_x='LMARGIN', new_y='NEXT')
                else:
                    self.set_font('Helvetica', '', font_size)
                    self.multi_cell(0, line_height, stripped, markdown=True,
                                    new_x='LMARGIN', new_y='NEXT')
            self.ln(1.5)

    def render_insight_section(self, section: dict):
        """Render one analytical section with a tone-accented heading bar."""
        tone = section.get('tone', 'neutral')
        accent = self.TONE_COLORS.get(tone, self.TONE_COLORS['neutral'])

        # Accent + title bar
        self.set_fill_color(*accent)
        self.rect(self.l_margin, self.get_y(), 2.2, 7, 'F')
        self.set_x(self.l_margin + 5)
        self.set_font('Helvetica', 'B', 11)
        self.set_text_color(*accent)
        self.cell(0, 7, _sanitize_pdf_text(section.get('title', 'Insights')),
                  new_x='LMARGIN', new_y='NEXT')
        self.ln(1)
        self.render_markdown(section.get('content', ''), font_size=9)
        self.ln(3)

    def render_highlights(self, highlights: list):
        """Render KPI highlight cards in a grid."""
        if not highlights:
            return
        card_w = (self.w - self.l_margin - self.r_margin - 6) / 3
        card_h = 16
        x_start = self.l_margin
        for i, hl in enumerate(highlights[:6]):
            col = i % 3
            row = i // 3
            if col == 0 and row > 0:
                self.ln(card_h + 4)
            x = x_start + col * (card_w + 3)
            y = self.get_y() + row * (card_h + 4)
            tone = hl.get('tone', 'neutral')
            accent = self.TONE_COLORS.get(tone, self.TONE_COLORS['neutral'])

            # Card background
            self.set_fill_color(*self.BG_ALT)
            self.rect(x, y, card_w, card_h, 'F')
            # Accent top border
            self.set_fill_color(*accent)
            self.rect(x, y, card_w, 1.2, 'F')

            self.set_xy(x + 3, y + 2.5)
            self.set_font('Helvetica', '', 7)
            self.set_text_color(148, 163, 184)
            self.multi_cell(card_w - 6, 3, _sanitize_pdf_text(hl.get('label', '')).upper())
            self.set_xy(x + 3, y + 8)
            self.set_font('Helvetica', 'B', 9)
            self.set_text_color(255, 255, 255)
            self.multi_cell(card_w - 6, 4, _sanitize_pdf_text(hl.get('value', '')))
            if hl.get('delta'):
                self.set_xy(x + 3, y + 12.5)
                self.set_font('Helvetica', '', 7)
                self.set_text_color(*accent)
                self.cell(card_w - 6, 3, _sanitize_pdf_text(hl['delta']))

        # Advance cursor past the last row
        rows = (min(len(highlights), 6) - 1) // 3 + 1
        self.set_y(self.get_y() + rows * (card_h + 4))
        self.ln(2)

    def render_insights(self, insights: dict):
        """Render the full structured AI/heuristic insights block."""
        if not insights or (not insights.get('sections') and not insights.get('executive_summary')):
            return

        # Executive summary callout
        exec_text = _sanitize_pdf_text(insights.get('executive_summary') or '').strip()
        if exec_text:
            self.set_fill_color(34, 42, 70)
            self.rect(self.l_margin, self.get_y(),
                      self.w - self.l_margin - self.r_margin, 4, 'F')  # thin top accent
            self.set_fill_color(52, 211, 153)
            self.rect(self.l_margin, self.get_y(),
                      self.w - self.l_margin - self.r_margin, 1.2, 'F')
            self.set_xy(self.l_margin, self.get_y() + 2)
            self.set_font('Helvetica', 'B', 11)
            self.set_text_color(52, 211, 153)
            self.cell(0, 7, 'EXECUTIVE SUMMARY', new_x='LMARGIN', new_y='NEXT')
            self.ln(1)
            self.render_markdown(exec_text, font_size=10, line_height=5.5)
            self.ln(4)

        # Highlights
        if insights.get('highlights'):
            self.section_label('At a Glance')
            self.render_highlights(insights['highlights'])
            self.ln(2)

        # Sections
        for section in insights.get('sections', []):
            self.render_insight_section(section)

        # Recommendations
        recs = insights.get('recommendations', [])
        if recs:
            self.ln(2)
            self.set_fill_color(52, 211, 153)
            self.rect(self.l_margin, self.get_y(), 2.2, 7, 'F')
            self.set_x(self.l_margin + 5)
            self.set_font('Helvetica', 'B', 11)
            self.set_text_color(52, 211, 153)
            self.cell(0, 7, 'Recommended Actions', new_x='LMARGIN', new_y='NEXT')
            self.ln(1)
            for i, rec in enumerate(recs, 1):
                self.set_font('Helvetica', 'B', 9)
                self.set_text_color(52, 211, 153)
                self.set_x(self.l_margin + 2)
                self.cell(6, 5.5, f'{i}.')
                self.set_text_color(226, 232, 240)
                self.set_x(self.l_margin + 8)
                self.set_font('Helvetica', '', 9)
                self.multi_cell(self.w - self.l_margin - 8 - self.r_margin,
                                5.5, _sanitize_pdf_text(rec), markdown=True,
                                new_x='LMARGIN', new_y='NEXT')
            self.ln(2)

        # Source attribution
        source = insights.get('source', 'heuristic')
        self.ln(1)
        self.set_font('Helvetica', 'I', 7)
        self.set_text_color(100, 116, 139)
        label = (
            'AI-generated analysis'
            if source == 'llm'
            else 'Deterministic analysis from verified GODFIN calculations'
        )
        self.cell(0, 4, label, new_x='LMARGIN', new_y='NEXT')


def generate_summary_pdf(db: Session, month: str) -> bytes:
    summary = prepare_summary_report(db, month)
    trend = _get_spending_trend(db, month)
    detailed = prepare_detailed_report(db, month)
    insights = generate_deterministic_insights(detailed, trend)

    # Generate charts
    cat_chart = generate_category_chart(summary['all_categories'])
    trend_chart = generate_trend_chart(trend)

    month_label = date(int(month[:4]), int(month[5:7]), 1).strftime('%B %Y')

    pdf = ReportPDF()
    pdf._report_title = 'GODFIN Monthly Report'
    pdf._report_subtitle = month_label
    pdf.set_auto_page_break(auto=True, margin=20)

    # Cover page
    pdf.add_cover_page('GODFIN', 'Monthly Financial Report', month_label)

    pdf.add_page()

    # Key metrics
    pdf.section_label('Key Metrics')
    pdf.stat_line('Total Spend', f'Rs {_format_inr(summary["total_spend"])}')
    pdf.stat_line('Total Income', f'Rs {_format_inr(summary["total_income"])}')
    sr = summary['savings_rate']
    sr_color = ReportPDF.TONE_COLORS.get(
        _tone_for_savings(
            sr,
            summary['savings_target_percent'],
            assessment_available=summary['savings_target_assessment_available'],
        ),
        (255, 255, 255),
    )
    pdf.stat_line('Savings Rate', f'{sr}%' if sr is not None else 'N/A', value_color=sr_color)
    pdf.stat_line('Savings Target', f'{summary["savings_target_percent"]}%')
    pdf.stat_line('Period Status', summary['period_status'].title())
    pdf.stat_line('Transactions', str(summary['transaction_count']))
    pdf.stat_line('Avg Transaction', f'Rs {_format_inr(summary["avg_transaction"])}')
    pdf.stat_line('Recurring Total', f'Rs {_format_inr(summary["recurring_total"])}')
    pdf.ln(4)

    # Spending by type
    pdf.section_label('Spending by Type')
    for label, key in [('Fixed', 'fixed'), ('Semi-Flexible', 'semi_flexible'), ('Flexible', 'flexible')]:
        pdf.stat_line(label, f'Rs {_format_inr(summary["spending_by_elasticity"].get(key, 0))}')
    pdf.ln(4)

    # Category chart
    if summary['all_categories']:
        pdf.section_label('Category Breakdown')
        pdf.image(io.BytesIO(cat_chart), x=15, w=120)
        pdf.ln(4)

    # Top categories
    if summary['top_categories']:
        pdf.section_label('Top Categories')
        pdf.set_font('Helvetica', '', 9)
        for i, cat in enumerate(summary['top_categories'], 1):
            pct = round(cat['amount'] / summary['total_spend'] * 100, 1) if summary['total_spend'] > 0 else 0
            pdf.set_text_color(148, 163, 184)
            pdf.cell(8, 6, f'{i}.')
            pdf.cell(62, 6, cat['category'])
            pdf.set_text_color(255, 255, 255)
            pdf.cell(35, 6, f'Rs {_format_inr(cat["amount"])}')
            pdf.set_text_color(100, 116, 139)
            pdf.cell(0, 6, f'{pct}%', new_x='LMARGIN', new_y='NEXT')
        pdf.ln(4)

    # Trend chart
    pdf.section_label('Finished-Month Spending Trend')
    pdf.image(io.BytesIO(trend_chart), x=15, w=140)
    pdf.ln(6)

    # AI insights
    pdf.add_page()
    pdf.section_label('Financial Insights')
    pdf.ln(2)
    pdf.render_insights(insights)

    return bytes(pdf.output())


def generate_detailed_pdf(
    db: Session,
    month: str,
    *,
    ai_metadata: dict,
) -> bytes:
    if not ai_metadata or not ai_metadata.get('consent', {}).get('provided'):
        raise ValueError("AI report metadata with explicit consent is required")
    detailed = prepare_detailed_report(db, month)
    trend = _get_spending_trend(db, month)
    insights = generate_ai_financial_insights(detailed, trend)

    # Generate all charts
    cat_chart = generate_category_chart(detailed['all_categories'])
    trend_chart = generate_trend_chart(trend)
    daily_chart = generate_daily_chart(detailed.get('daily_spending', []))

    month_label = date(int(month[:4]), int(month[5:7]), 1).strftime('%B %Y')

    pdf = ReportPDF()
    pdf._report_title = 'GODFIN Detailed Report'
    pdf._report_subtitle = month_label
    pdf.set_auto_page_break(auto=True, margin=20)

    # Cover page
    pdf.add_cover_page('GODFIN', 'Detailed Financial Report', month_label)

    pdf.add_page()

    # Key metrics
    pdf.section_label('Key Metrics')
    pdf.stat_line('Total Spend', f'Rs {_format_inr(detailed["total_spend"])}')
    pdf.stat_line('Total Income', f'Rs {_format_inr(detailed["total_income"])}')
    sr = detailed['savings_rate']
    sr_color = ReportPDF.TONE_COLORS.get(
        _tone_for_savings(
            sr,
            detailed['savings_target_percent'],
            assessment_available=detailed['savings_target_assessment_available'],
        ),
        (255, 255, 255),
    )
    pdf.stat_line('Savings Rate', f'{sr}%' if sr is not None else 'N/A', value_color=sr_color)
    pdf.stat_line('Savings Target', f'{detailed["savings_target_percent"]}%')
    pdf.stat_line('Period Status', detailed['period_status'].title())
    pdf.stat_line('Transactions', str(detailed['transaction_count']))
    pdf.ln(4)

    pdf.section_label('AI Report Disclosure')
    provider = ai_metadata.get('llm', {})
    pdf.stat_line(
        'Provider',
        _sanitize_pdf_text(
            f"{provider.get('provider', 'AI')} / {provider.get('model', 'configured model')}"
        ),
    )
    pdf.stat_line(
        'Generated',
        _sanitize_pdf_text(ai_metadata.get('generated_at', 'timestamp unavailable')),
    )
    shared = ai_metadata.get('data_disclosure', {}).get('shared', [])
    pdf.render_markdown(
        "Data provided to the connected AI:\n" + "\n".join(f"- {item}" for item in shared),
        font_size=8,
    )
    pdf.ln(4)

    # Category chart
    if detailed['all_categories']:
        pdf.section_label('Category Breakdown')
        pdf.image(io.BytesIO(cat_chart), x=15, w=120)
        pdf.ln(4)

    # Full category table
    if detailed['all_categories']:
        pdf.section_label('All Categories')
        pdf.set_font('Helvetica', '', 9)
        for i, cat in enumerate(detailed['all_categories'], 1):
            pct = round(cat['amount'] / detailed['total_spend'] * 100, 1) if detailed['total_spend'] > 0 else 0
            pdf.set_text_color(148, 163, 184)
            pdf.cell(8, 6, f'{i}.')
            pdf.cell(62, 6, cat['category'])
            pdf.set_text_color(255, 255, 255)
            pdf.cell(35, 6, f'Rs {_format_inr(cat["amount"])}')
            pdf.set_text_color(100, 116, 139)
            pdf.cell(0, 6, f'{pct}%', new_x='LMARGIN', new_y='NEXT')
        pdf.ln(4)

    # Top merchants
    if detailed.get('top_merchants'):
        pdf.section_label('Top Merchants')
        pdf.set_font('Helvetica', '', 9)
        for m in detailed['top_merchants']:
            pdf.set_text_color(226, 232, 240)
            pdf.cell(70, 6, (m['merchant'] or 'Unknown')[:30])
            pdf.set_text_color(255, 255, 255)
            pdf.cell(35, 6, f'Rs {_format_inr(m["amount"])}')
            pdf.set_text_color(100, 116, 139)
            pdf.cell(0, 6, f'{m["count"]}x', new_x='LMARGIN', new_y='NEXT')
        pdf.ln(4)

    # Daily spending chart
    pdf.section_label('Daily Spending')
    pdf.image(io.BytesIO(daily_chart), x=15, w=140)
    pdf.ln(4)

    # Trend chart
    pdf.section_label('Finished-Month Spending Trend')
    pdf.image(io.BytesIO(trend_chart), x=15, w=140)
    pdf.ln(4)

    # Category comparison (new page)
    if detailed.get('category_comparison'):
        pdf.add_page()
        pdf.section_label(
            f"Category vs {detailed['category_comparison_sample_size']}-Recorded-Month Average"
        )
        pdf.set_font('Helvetica', '', 9)
        for comp in detailed['category_comparison']:
            diff = comp['current'] - comp['average']
            arrow = '+' if diff > 0 else ''
            pdf.set_text_color(226, 232, 240)
            pdf.cell(55, 6, comp['category'][:25])
            pdf.set_text_color(255, 255, 255)
            pdf.cell(30, 6, f'Rs {_format_inr(comp["current"])}')
            pdf.set_text_color(148, 163, 184)
            pdf.cell(30, 6, f'Avg: Rs {_format_inr(comp["average"])}')
            color = (248, 113, 113) if diff > 0 else (52, 211, 153)
            pdf.set_text_color(*color)
            pdf.cell(0, 6, f'{arrow}{_format_inr(abs(diff))}', new_x='LMARGIN', new_y='NEXT')
        pdf.ln(4)

    # Recurring
    if detailed.get('recurring_list'):
        pdf.section_label('Recurring Expenses')
        pdf.set_font('Helvetica', '', 9)
        for r in detailed['recurring_list']:
            pdf.set_text_color(226, 232, 240)
            pdf.cell(55, 6, (r['merchant'] or 'Unknown')[:25])
            pdf.set_text_color(255, 255, 255)
            pdf.cell(30, 6, f'Rs {_format_inr(r["amount"])}')
            pdf.set_text_color(100, 116, 139)
            pdf.cell(0, 6, r['frequency'], new_x='LMARGIN', new_y='NEXT')
        pdf.ln(4)

    # AI insights (new page)
    pdf.add_page()
    pdf.section_label('Financial Insights')
    pdf.ln(2)
    pdf.render_insights(insights)

    return bytes(pdf.output())
