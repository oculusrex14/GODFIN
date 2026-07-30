from __future__ import annotations

import io
import json
import logging
import re
from datetime import date, datetime
from typing import Optional

from fpdf import FPDF
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.budget import ELASTICITY
from app.core.llm_service import call_llm, estimate_tokens
from app.models.recurring_pattern import RecurringPattern
from app.models.transaction import Transaction

logger = logging.getLogger(__name__)

CHART_DPI = 300


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


# --- Data Preparation ---

def prepare_summary_report(db: Session, month: str) -> dict:
    start, end = _month_range(month)

    base = db.query(Transaction).filter(
        Transaction.date >= start,
        Transaction.date < end,
        Transaction.status != 'deleted',
    )

    total_spend = float(
        base.filter(Transaction.type == 'debit', Transaction.is_transfer == False)
        .with_entities(func.coalesce(func.sum(Transaction.amount), 0))
        .scalar()
    )

    total_income = float(
        base.filter(Transaction.is_income == True)
        .with_entities(func.coalesce(func.sum(Transaction.amount), 0))
        .scalar()
    )

    savings_rate = None
    if total_income > 0:
        savings_rate = round(((total_income - total_spend) / total_income) * 100, 1)

    transaction_count = base.filter(
        Transaction.type == 'debit', Transaction.is_transfer == False
    ).count()

    avg_transaction = round(total_spend / transaction_count, 2) if transaction_count > 0 else 0

    # Category breakdown
    category_rows = (
        base.filter(
            Transaction.type == 'debit',
            Transaction.is_transfer == False,
            Transaction.category.isnot(None),
        )
        .with_entities(Transaction.category, func.sum(Transaction.amount).label('total'))
        .group_by(Transaction.category)
        .order_by(func.sum(Transaction.amount).desc())
        .all()
    )
    categories = [
        {'category': r.category, 'amount': round(float(r.total), 2)}
        for r in category_rows
    ]

    # Elasticity breakdown
    elasticity = {'fixed': 0, 'semi_flexible': 0, 'flexible': 0}
    for cat_row in categories:
        elast = ELASTICITY.get(cat_row['category'], 'flexible')
        if elast in elasticity:
            elasticity[elast] += cat_row['amount']
    elasticity = {k: round(v, 2) for k, v in elasticity.items()}

    # Recurring total
    recurring_total = float(
        db.query(func.coalesce(func.sum(RecurringPattern.avg_amount), 0))
        .filter(RecurringPattern.is_active == True, RecurringPattern.frequency == 'monthly')
        .scalar()
    )
    financial_health_score = None
    financial_health_label = "Add income to calculate"
    health_components = {}
    if total_income > 0:
        savings_value = savings_rate or 0.0
        savings_points = max(0.0, min(55.0, (savings_value + 10.0) / 50.0 * 55.0))
        coverage_points = max(
            0.0,
            min(25.0, (1.0 - max(0.0, total_spend - total_income) / total_income) * 25.0),
        )
        subscription_share = recurring_total / total_income
        commitment_points = max(0.0, min(20.0, (1.0 - subscription_share) * 20.0))
        financial_health_score = round(
            savings_points + coverage_points + commitment_points
        )
        if financial_health_score >= 75:
            financial_health_label = "Strong breathing room"
        elif financial_health_score >= 50:
            financial_health_label = "Some breathing room"
        else:
            financial_health_label = "Money may feel tight"
        health_components = {
            "money_left_after_spending": round(savings_points, 1),
            "income_coverage": round(coverage_points, 1),
            "room_after_subscriptions": round(commitment_points, 1),
        }

    return {
        'month': month,
        'total_spend': round(total_spend, 2),
        'total_income': round(total_income, 2),
        'savings_rate': savings_rate,
        'transaction_count': transaction_count,
        'avg_transaction': avg_transaction,
        'top_categories': categories[:5],
        'all_categories': categories,
        'spending_by_elasticity': elasticity,
        'recurring_total': round(recurring_total, 2),
        'financial_health_score': financial_health_score,
        'financial_health_label': financial_health_label,
        'financial_health_components': health_components,
        'financial_health_caveat': (
            "A simple monthly summary from recorded income, spending, and confirmed "
            "recurring costs. It is not a credit score or financial diagnosis."
        ),
    }


def prepare_detailed_report(db: Session, month: str) -> dict:
    summary = prepare_summary_report(db, month)
    start, end = _month_range(month)

    base = db.query(Transaction).filter(
        Transaction.date >= start,
        Transaction.date < end,
        Transaction.status != 'deleted',
    )

    # Top merchants by spend
    merchant_rows = (
        base.filter(
            Transaction.type == 'debit',
            Transaction.is_transfer == False,
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
            Transaction.type == 'debit',
            Transaction.is_transfer == False,
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

    # Category comparison: this month vs trailing 3-month average (relative to the
    # report month, NOT today — so viewing a past month compares against the period
    # that actually preceded it).
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
            Transaction.type == 'debit',
            Transaction.is_transfer == False,
            Transaction.category.isnot(None),
        )
        .group_by(Transaction.category)
        .all()
    )

    # Average over the 3 months preceding the report month
    months_in_period = 3
    avg_by_cat = {r.category: round(float(r.total) / months_in_period, 2) for r in avg_rows}

    category_comparison = []
    for cat_row in summary['all_categories']:
        cat = cat_row['category']
        category_comparison.append({
            'category': cat,
            'current': cat_row['amount'],
            'average': avg_by_cat.get(cat, 0),
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
            'amount': p.avg_amount,
            'frequency': p.frequency,
            'category': p.category,
        }
        for p in patterns
    ]

    income_rows = (
        base.filter(Transaction.is_income == True)
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
        'recurring_list': recurring_list,
        'income_breakdown': income_breakdown,
    }


# --- Spending Trend (reuse dashboard logic) ---

def _get_spending_trend(db: Session, month: str, num_months: int = 6) -> list:
    year, mon = int(month[:4]), int(month[5:7])
    result = []

    for i in range(num_months - 1, -1, -1):
        m = mon - i
        y = year
        while m <= 0:
            m += 12
            y -= 1

        m_start = date(y, m, 1)
        m_end = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)

        spend = float(
            db.query(func.coalesce(func.sum(Transaction.amount), 0))
            .filter(
                Transaction.date >= m_start,
                Transaction.date < m_end,
                Transaction.status != 'deleted',
                Transaction.type == 'debit',
                Transaction.is_transfer == False,
            )
            .scalar()
        )
        income = float(
            db.query(func.coalesce(func.sum(Transaction.amount), 0))
            .filter(
                Transaction.date >= m_start,
                Transaction.date < m_end,
                Transaction.status != 'deleted',
                Transaction.is_income == True,
            )
            .scalar()
        )
        result.append({
            'month': f'{y}-{m:02d}',
            'label': m_start.strftime('%b'),
            'spend': round(spend, 2),
            'income': round(income, 2),
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

# Insight schema (returned by generate_financial_insights):
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


def _tone_for_savings(savings_rate):
    if savings_rate is None:
        return 'neutral'
    if savings_rate >= 30:
        return 'positive'
    if savings_rate >= 10:
        return 'neutral'
    if savings_rate >= 0:
        return 'warning'
    return 'negative'


def _pct(part: float, whole: float) -> float:
    return round((part / whole) * 100, 1) if whole > 0 else 0.0


def _build_insights_prompt(detailed: dict, trend: list, month_label: str) -> str:
    s = detailed
    elastic = s.get('spending_by_elasticity', {})
    top_cats = s.get('top_categories', [])
    cats_lines = '\n'.join(
        f"  - {c['category']}: Rs {_format_inr(c['amount'])} ({_pct(c['amount'], s['total_spend'])}% of spend)"
        for c in top_cats
    ) or '  - (none)'

    comp_lines = '\n'.join(
        f"  - {c['category']}: this month Rs {_format_inr(c['current'])} vs 3-mo avg Rs {_format_inr(c['average'])}"
        f" (delta {('+' if c['current'] - c['average'] >= 0 else '')}Rs {_format_inr(c['current'] - c['average'])})"
        for c in s.get('category_comparison', [])[:8]
    ) or '  - (none)'

    merch_lines = '\n'.join(
        f"  - {m['merchant'] or 'Unknown'}: Rs {_format_inr(m['amount'])} across {m['count']} transactions"
        for m in s.get('top_merchants', [])[:6]
    ) or '  - (none)'

    recur_lines = '\n'.join(
        f"  - {r['merchant'] or 'Unknown'} ({r['category']}): Rs {_format_inr(r['amount'])} / {r['frequency']}"
        for r in s.get('recurring_list', [])[:8]
    ) or '  - (none)'

    trend_lines = '\n'.join(
        f"  - {t['month']}: spend Rs {_format_inr(t['spend'])}, income Rs {_format_inr(t['income'])}"
        for t in trend
    ) or '  - (none)'

    return f"""You are writing a careful, plain-language monthly money report for an Indian
user. All amounts are in Indian Rupees (Rs). The report month is {month_label}.

Use ONLY the data below. Do not invent figures. Be specific, quantitative, and actionable — reference
real numbers and category names from the data. Explain finance terms in everyday language. Do not
diagnose the user, shame spending, or claim certainty that the data cannot support.

=== FINANCIAL DATA ===
Total Spend: Rs {_format_inr(s.get('total_spend', 0))}
Total Income: Rs {_format_inr(s.get('total_income', 0))}
Savings Rate: {s.get('savings_rate', 'N/A')}%
Transactions: {s.get('transaction_count', 0)}
Average Transaction: Rs {_format_inr(s.get('avg_transaction', 0))}

Spending by elasticity:
  - Fixed: Rs {_format_inr(elastic.get('fixed', 0))}
  - Semi-Flexible: Rs {_format_inr(elastic.get('semi_flexible', 0))}
  - Flexible: Rs {_format_inr(elastic.get('flexible', 0))}
Recurring monthly total: Rs {_format_inr(s.get('recurring_total', 0))}

Top categories:
{cats_lines}

Category vs trailing 3-month average:
{comp_lines}

Top merchants:
{merch_lines}

Recurring subscriptions/commitments:
{recur_lines}

Last 6 months trend (oldest → newest):
{trend_lines}
=== END DATA ===

Respond with ONLY a JSON object (no prose, no markdown fences) in EXACTLY this shape:
{{
  "executive_summary": "2-4 sentence markdown overview of the month's financial position.",
  "sections": [
    {{"title": "Spending Breakdown", "tone": "neutral", "icon": "pie", "content": "markdown: where the money went, top categories with Rs and %, what stands out"}},
    {{"title": "Savings Health", "tone": "<positive|warning|negative|neutral>", "icon": "piggy", "content": "markdown: assess the savings rate vs the 20% benchmark, income vs spend balance"}},
    {{"title": "Trend & Momentum", "tone": "neutral", "icon": "trend", "content": "markdown: compare this month to the 6-month trend, is spending accelerating or cooling"}},
    {{"title": "Watch-outs", "tone": "<positive|warning|negative|neutral>", "icon": "alert", "content": "markdown: categories spiking vs their 3-mo average, flexible spend risks, recurring creep"}}
  ],
  "highlights": [
    {{"label": "Biggest Category", "value": "Rs X (Y%)", "tone": "neutral", "delta": null}},
    {{"label": "Flexible Spend", "value": "Rs X (Y%)", "tone": "warning", "delta": null}},
    {{"label": "Top Spike vs Avg", "value": "Category +Rs X", "tone": "negative", "delta": null}}
  ],
  "recommendations": [
    "markdown bullet: one specific, prioritized action with a Rs target",
    "markdown bullet: a second concrete action",
    "markdown bullet: a third forward-looking action for next month"
  ]
}}

Rules:
- "tone" must be one of: positive, warning, negative, neutral.
- "icon" must be one of: pie, piggy, trend, alert, wallet, repeat.
- Keep executive_summary to 2-4 sentences. Each section's content: 3-6 sentences of markdown (use **bold** for category/amount anchors, and bullet lists where natural).
- 3 recommendations max, each a single bullet string.
- Reference real numbers from the data. No generic platitudes."""


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
    # Minimal shape validation / normalization
    if not isinstance(data.get('sections'), list):
        return None
    for sec in data['sections']:
        sec['tone'] = sec.get('tone') if sec.get('tone') in INSIGHT_TONES else 'neutral'
        sec.setdefault('icon', 'wallet')
        sec.setdefault('content', '')
        sec.setdefault('title', 'Insights')
    if not isinstance(data.get('recommendations'), list):
        data['recommendations'] = []
    if not isinstance(data.get('highlights'), list):
        data['highlights'] = []
    data.setdefault('executive_summary', '')
    return data


def _heuristic_insights(detailed: dict, trend: list) -> dict:
    """Deterministic, data-driven structured report used when the LLM is unavailable.
    Always produces a complete, meaningful report from the numbers."""
    s = detailed
    spend = s.get('total_spend', 0)
    income = s.get('total_income', 0)
    savings = s.get('savings_rate')
    elastic = s.get('spending_by_elasticity', {})
    fixed = elastic.get('fixed', 0)
    flex = elastic.get('flexible', 0)
    semi = elastic.get('semi_flexible', 0)
    top = s.get('top_categories', [])
    comp = s.get('category_comparison', [])
    recurring = s.get('recurring_total', 0)

    # Executive summary
    if spend == 0 and income == 0:
        exec_sum = "No transactions were recorded for this period, so there is nothing to analyse yet. " \
                   "Once alerts are ingested, this report will populate automatically."
    elif savings is not None and savings >= 30:
        exec_sum = f"**{month_label_of(s)}** was a strong month: you saved **{savings:.1f}%** of income " \
                   f"(Rs {_format_inr(income - spend)} of Rs {_format_inr(income)}). Spending stayed at " \
                   f"Rs {_format_inr(spend)} across {s.get('transaction_count', 0)} transactions."
    elif savings is not None and savings >= 0:
        exec_sum = f"In **{month_label_of(s)}** you spent Rs {_format_inr(spend)} against income of " \
                   f"Rs {_format_inr(income)}, saving **{savings:.1f}%**. There is room to tighten " \
                   f"discretionary spend and push the savings rate toward the 20% benchmark."
    elif savings is not None:
        exec_sum = f"**{month_label_of(s)}** ran a deficit: spending of Rs {_format_inr(spend)} exceeded " \
                   f"income of Rs {_format_inr(income)} by Rs {_format_inr(spend - income)}. Priority " \
                   f"this month is reining in flexible expenses."
    else:
        exec_sum = f"You recorded Rs {_format_inr(spend)} of spending across " \
                   f"{s.get('transaction_count', 0)} transactions in **{month_label_of(s)}**. " \
                   f"Add income transactions to enable savings-rate analysis."

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

    # Savings Health section
    tone_s = _tone_for_savings(savings)
    if savings is not None:
        if savings >= 30:
            health = f"A **{savings:.1f}%** savings rate is well above the 20% healthy benchmark — " \
                     f"you kept Rs {_format_inr(income - spend)} of every Rs {_format_inr(income)} earned."
        elif savings >= 20:
            health = f"At **{savings:.1f}%**, you meet the 20% benchmark. Maintaining this consistently " \
                     f"builds a strong cushion."
        elif savings >= 10:
            health = f"Your **{savings:.1f}%** savings rate sits below the 20% benchmark. Trimming " \
                     f"flexible spend by Rs {_format_inr(flex * 0.25)} would close most of the gap."
        elif savings >= 0:
            health = f"Only **{savings:.1f}%** of income was saved — below the 20% benchmark. " \
                     f"Discretionary categories are the fastest lever to improve this."
        else:
            health = f"Negative savings of **{savings:.1f}%** means spending outran income by " \
                     f"Rs {_format_inr(spend - income)}. This is unsustainable month-over-month."
    else:
        health = "No income was recorded, so a savings rate can't be calculated. " \
                 "Log salary/credit transactions to unlock this analysis."
    sections.append({'title': 'Savings Health', 'tone': tone_s, 'icon': 'piggy', 'content': health})

    # Trend & Momentum section
    if trend and len(trend) >= 2:
        cur = trend[-1]
        prev = trend[-2]
        spend_delta = cur['spend'] - prev['spend']
        direction = "up" if spend_delta > 0 else "down"
        # 6-mo average spend
        avg6 = sum(t['spend'] for t in trend) / len(trend)
        vs_avg = cur['spend'] - avg6
        momentum = (f"This month's spend of Rs {_format_inr(cur['spend'])} is {direction} "
                    f"Rs {_format_inr(abs(spend_delta))} versus last month "
                    f"(Rs {_format_inr(prev['spend'])}), and "
                    f"{'above' if vs_avg > 0 else 'below'} the 6-month average of "
                    f"Rs {_format_inr(avg6)} by Rs {_format_inr(abs(vs_avg))}.")
    else:
        momentum = "Not enough history yet to establish a spending trend — two or more months of " \
                   "data are needed."
    sections.append({'title': 'Trend & Momentum', 'tone': 'neutral', 'icon': 'trend', 'content': momentum})

    # Watch-outs section
    spikes = []
    for c in comp:
        diff = c['current'] - c['average']
        if c['average'] > 0 and diff / c['average'] >= 0.25:
            spikes.append((c['category'], diff, c['current'], c['average']))
    spikes.sort(key=lambda x: x[1], reverse=True)

    watch_lines = []
    if spikes:
        for cat, diff, cur, avg in spikes[:3]:
            pct_inc = round((diff / avg) * 100) if avg > 0 else 0
            watch_lines.append(f"**{cat}** is running Rs {_format_inr(diff)} (+{pct_inc}%) above its "
                               f"3-month average (Rs {_format_inr(avg)} → Rs {_format_inr(cur)})")
    if flex > 0 and _pct(flex, spend) > 40:
        watch_lines.append(f"Flexible spend dominates at {_pct(flex, spend)}% of total — this is the "
                           f"easiest category to cut in a tight month")
    if recurring > 0 and income > 0 and recurring / income > 0.3:
        watch_lines.append(f"Recurring commitments of Rs {_format_inr(recurring)} already absorb "
                           f"{round(recurring / income * 100)}% of income before discretionary spend")
    if not watch_lines:
        watch_lines.append("No categories are spiking materially versus their trailing average, and "
                           "the fixed/flexible balance looks stable.")
    watch_tone = 'warning' if len(watch_lines) > 1 else ('neutral' if not spikes else 'warning')
    sections.append({
        'title': 'Watch-outs',
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
            'label': 'Savings Rate',
            'value': f"{savings:.1f}%",
            'tone': _tone_for_savings(savings),
            'delta': f"of Rs {_format_inr(income)}",
        })

    # Recommendations
    recs = []
    if spikes:
        cat, diff, _, _ = spikes[0]
        recs.append(f"**Audit {cat} first** — it is Rs {_format_inr(diff)} above its 3-month average. "
                    f"Review the underlying transactions and set a ceiling of Rs "
                    f"{_format_inr(spikes[0][3])} for next month.")
    if savings is not None and savings < 20 and flex > 0:
        target = round(flex * 0.20)
        recs.append(f"**Trim flexible spend by ~Rs {_format_inr(target)}** next month to move the "
                    f"savings rate from {savings:.1f}% toward the 20% benchmark.")
    if recurring > 0:
        recs.append(f"**Review recurring commitments** totalling Rs {_format_inr(recurring)} — cancel "
                    f"unused subscriptions to free up monthly margin.")
    if not recs:
        recs.append("Keep doing what you're doing — spending is within historical norms. "
                    "Redirect surplus savings toward an emergency fund or investment.")
        recs.append("Continue logging income transactions so savings-rate tracking stays accurate.")

    return {
        'available': True,
        'source': 'heuristic',
        'executive_summary': exec_sum,
        'sections': sections,
        'highlights': highlights,
        'recommendations': recs,
    }


def month_label_of(detailed: dict) -> str:
    m = detailed.get('month')
    if not m:
        return 'this month'
    try:
        return date(int(m[:4]), int(m[5:7]), 1).strftime('%B %Y')
    except Exception:
        return 'this month'


def generate_financial_insights(
    detailed: dict,
    trend: list,
    *,
    require_llm: bool = False,
) -> dict:
    """Produce a structured professional financial report.

    Tries the LLM first (rich, advisor-quality narrative). Falls back to a
    deterministic heuristic report built from the numbers for non-AI callers.
    AI-labelled reports can require a real LLM response so a heuristic result is
    never presented as model-authored.
    """
    month_label = month_label_of(detailed)

    # Not enough data → return a minimal empty-state report
    if detailed.get('total_spend', 0) == 0 and detailed.get('total_income', 0) == 0 \
            and detailed.get('transaction_count', 0) == 0:
        if require_llm:
            raise DetailedReportUnavailable(
                f"No recorded activity is available for {month_label}."
            )
        return {
            'available': False,
            'source': 'none',
            'executive_summary': f"No transactions recorded for {month_label}. Ingest Gmail alerts or "
                                 f"upload a statement to populate this report.",
            'sections': [],
            'highlights': [],
            'recommendations': [],
        }

    prompt = _build_insights_prompt(detailed, trend, month_label)
    try:
        raw = call_llm(prompt, temperature=0.5)
    except Exception as e:
        logger.warning(f"LLM insights call failed: {e}")
        raw = None

    if raw:
        parsed = _parse_insights_json(raw)
        if parsed:
            parsed['available'] = True
            parsed['source'] = 'llm'
            parsed.setdefault('executive_summary', '')
            return parsed
        logger.warning("LLM insights returned unparseable JSON; falling back to heuristic")

    if require_llm:
        raise DetailedReportUnavailable(
            "The connected AI did not return a usable report. Check the model "
            "connection and try again; no AI commentary was generated."
        )
    return _heuristic_insights(detailed, trend)


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
        label = 'AI-generated analysis' if source == 'llm' else 'Statistical analysis (LLM unavailable)'
        self.cell(0, 4, label, new_x='LMARGIN', new_y='NEXT')


def generate_summary_pdf(db: Session, month: str) -> bytes:
    summary = prepare_summary_report(db, month)
    trend = _get_spending_trend(db, month)
    detailed = prepare_detailed_report(db, month)
    insights = generate_financial_insights(detailed, trend)

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
    sr_color = ReportPDF.TONE_COLORS.get(_tone_for_savings(sr), (255, 255, 255))
    pdf.stat_line('Savings Rate', f'{sr}%' if sr is not None else 'N/A', value_color=sr_color)
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
    pdf.section_label('Spending Trend (6 Months)')
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
    require_llm: bool = False,
) -> bytes:
    detailed = prepare_detailed_report(db, month)
    trend = _get_spending_trend(db, month)
    insights = generate_financial_insights(
        detailed,
        trend,
        require_llm=require_llm,
    )

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
    sr_color = ReportPDF.TONE_COLORS.get(_tone_for_savings(sr), (255, 255, 255))
    pdf.stat_line('Savings Rate', f'{sr}%' if sr is not None else 'N/A', value_color=sr_color)
    pdf.stat_line('Transactions', str(detailed['transaction_count']))
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
    pdf.section_label('Spending Trend (6 Months)')
    pdf.image(io.BytesIO(trend_chart), x=15, w=140)
    pdf.ln(4)

    # Category comparison (new page)
    if detailed.get('category_comparison'):
        pdf.add_page()
        pdf.section_label('Category vs 3-Month Average')
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
