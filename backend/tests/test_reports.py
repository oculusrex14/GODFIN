from __future__ import annotations

import io
import json
import uuid
from datetime import date

import pdfplumber

from app.core.reporting import (
    generate_category_chart,
    generate_daily_chart,
    generate_deterministic_insights,
    generate_trend_chart,
    month_label_of,
    prepare_detailed_report,
    prepare_summary_report,
)
from app.models.transaction import Transaction
from app.models.llm_config import LLMConfiguration
from app.seed import SAVINGS_ACCOUNT_ID


def _add_txn(db, merchant, amount, txn_date, category=None, txn_type='debit'):
    txn = Transaction(
        id=str(uuid.uuid4()),
        date=txn_date,
        raw_text=f'Test: {merchant} {amount}',
        merchant_raw=merchant,
        merchant_normalized=merchant.upper(),
        amount=amount,
        type=txn_type,
        instrument='upi',
        account_id=SAVINGS_ACCOUNT_ID,
        source='manual',
        category=category,
        is_income=txn_type == 'credit',
    )
    db.add(txn)
    return txn


def _activate_test_llm(db):
    db.add(
        LLMConfiguration(
            provider="ollama_local",
            auth_method="none",
            model="qwen-test",
            base_url="http://127.0.0.1:11434",
            is_active=True,
        )
    )
    db.commit()


def _valid_llm_report():
    return json.dumps(
        {
            "executive_summary": "Recorded income covered recorded spending.",
            "sections": [
                {
                    "title": "Spending Breakdown",
                    "tone": "neutral",
                    "icon": "pie",
                    "content": "Recorded spending was reviewed by category.",
                }
            ],
            "highlights": [],
            "recommendations": ["Review the largest flexible category."],
        }
    )


# --- Summary Report ---

def test_summary_report_empty(db_session):
    data = prepare_summary_report(db_session, '2025-01')
    assert data['total_spend'] == 0
    assert data['total_income'] == 0
    assert data['transaction_count'] == 0
    assert data['top_categories'] == []
    assert data['financial_health_score'] is None


def test_summary_report_with_data(db_session):
    _add_txn(db_session, 'SALARY', 75000, date(2025, 1, 1), category='INCOME', txn_type='credit')
    _add_txn(db_session, 'SWIGGY', 500, date(2025, 1, 5), category='FOOD & DINING')
    _add_txn(db_session, 'RENT', 20000, date(2025, 1, 3), category='HOUSING')
    _add_txn(db_session, 'NETFLIX', 199, date(2025, 1, 10), category='ENTERTAINMENT')
    db_session.flush()

    data = prepare_summary_report(db_session, '2025-01')
    assert data['total_spend'] == 20699.0
    assert data['total_income'] == 75000.0
    assert data['savings_rate'] is not None
    assert data['transaction_count'] == 3
    assert len(data['top_categories']) == 3
    assert data['top_categories'][0]['category'] == 'HOUSING'
    assert 0 <= data['financial_health_score'] <= 100
    assert data['financial_health_caveat']


# --- Detailed Report ---

def test_detailed_report_with_data(db_session):
    _add_txn(db_session, 'SALARY', 75000, date(2025, 1, 1), category='INCOME', txn_type='credit')
    _add_txn(db_session, 'SWIGGY', 500, date(2025, 1, 5), category='FOOD & DINING')
    _add_txn(db_session, 'SWIGGY', 300, date(2025, 1, 10), category='FOOD & DINING')
    _add_txn(db_session, 'RENT', 20000, date(2025, 1, 3), category='HOUSING')
    db_session.flush()

    data = prepare_detailed_report(db_session, '2025-01')
    assert 'top_merchants' in data
    assert len(data['top_merchants']) >= 1
    assert data['top_merchants'][0]['merchant'] == 'RENT'  # Highest spend
    assert 'daily_spending' in data
    assert 'category_comparison' in data
    assert data['income_breakdown'][0]['source'] == 'SALARY'


# --- Chart Generation ---

def test_category_chart_generation():
    data = [
        {'category': 'FOOD & DINING', 'amount': 5000},
        {'category': 'HOUSING', 'amount': 20000},
        {'category': 'ENTERTAINMENT', 'amount': 1000},
    ]
    png = generate_category_chart(data)
    assert isinstance(png, bytes)
    assert len(png) > 100
    # PNG magic bytes
    assert png[:4] == b'\x89PNG'


def test_trend_chart_generation():
    data = [
        {'label': 'Jan', 'spend': 20000, 'income': 75000},
        {'label': 'Feb', 'spend': 22000, 'income': 75000},
    ]
    png = generate_trend_chart(data)
    assert isinstance(png, bytes)
    assert png[:4] == b'\x89PNG'


def test_daily_chart_generation():
    data = [
        {'date': '2025-01-01', 'amount': 500},
        {'date': '2025-01-05', 'amount': 1200},
        {'date': '2025-01-10', 'amount': 800},
    ]
    png = generate_daily_chart(data)
    assert isinstance(png, bytes)
    assert png[:4] == b'\x89PNG'


def test_category_chart_empty():
    png = generate_category_chart([])
    assert isinstance(png, bytes)
    assert png[:4] == b'\x89PNG'


# --- Financial Insights ---

def test_insights_high_savings():
    detailed = {
        'month': '2025-01',
        'total_spend': 50000,
        'total_income': 75000,
        'savings_rate': 33.3,
        'transaction_count': 10,
        'top_categories': [{'category': 'HOUSING', 'amount': 20000}],
        'spending_by_elasticity': {'fixed': 20000, 'semi_flexible': 15000, 'flexible': 15000},
        'category_comparison': [],
        'recurring_total': 0,
    }
    insights = generate_deterministic_insights(detailed, [])
    assert insights['available'] is True
    assert insights['source'] == 'heuristic'
    assert 'executive_summary' in insights
    assert len(insights['sections']) >= 2
    assert 'Savings Health' in [s['title'] for s in insights['sections']]


def test_insights_no_data():
    detailed = {
        'month': '2025-01',
        'total_spend': 0,
        'total_income': 0,
        'savings_rate': None,
        'transaction_count': 0,
        'top_categories': [],
        'spending_by_elasticity': {'fixed': 0, 'semi_flexible': 0, 'flexible': 0},
        'category_comparison': [],
        'recurring_total': 0,
    }
    insights = generate_deterministic_insights(detailed, [])
    assert insights['available'] is False
    assert insights['source'] == 'none'
    assert 'not enough' in insights['executive_summary'].lower() or 'no transactions' in insights['executive_summary'].lower()


def test_month_label_of():
    assert month_label_of({'month': '2025-01'}) == 'January 2025'
    assert month_label_of({'month': '2025-12'}) == 'December 2025'
    assert month_label_of({}) == 'this month'


# --- API Endpoints ---

def test_summary_endpoint(auth_client):
    resp = auth_client.get('/api/v1/reports/summary?month=2025-01')
    assert resp.status_code == 200
    data = resp.json()
    assert 'total_spend' in data
    assert 'total_income' in data
    assert 'top_categories' in data


def test_detailed_endpoint(auth_client):
    resp = auth_client.get('/api/v1/reports/detailed?month=2025-01')
    assert resp.status_code == 200
    data = resp.json()
    assert 'top_merchants' in data
    assert 'daily_spending' in data
    assert 'category_comparison' in data


def test_insights_endpoint(auth_client, db_session, monkeypatch):
    from datetime import UTC, datetime

    from app.models.app_setting import AppSetting

    for key, value in {
        "license_tier": "pro",
        "license_status": "active",
        "license_verified_at": datetime.now(UTC).isoformat(),
    }.items():
        db_session.query(AppSetting).filter_by(key=key).one().value = value
    db_session.commit()
    _activate_test_llm(db_session)
    _add_txn(
        db_session,
        "SALARY",
        75000,
        date(2025, 1, 1),
        category="INCOME",
        txn_type="credit",
    )
    db_session.commit()
    monkeypatch.setattr(
        "app.core.reporting.call_llm",
        lambda *args, **kwargs: _valid_llm_report(),
    )

    resp = auth_client.post(
        '/api/v1/reports/ai/insights',
        json={'month': '2025-01', 'consent': True},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert 'month' in data
    assert 'insights' in data
    assert 'executive_summary' in data['insights']
    assert 'sections' in data['insights']
    assert data['insights']['source'] == 'llm'
    assert data['llm']['model'] == 'qwen-test'
    assert data['consent']['provided'] is True
    assert data['generated_at']
    assert 'raw transaction descriptions' in data['data_disclosure']['not_shared']


def test_detailed_reports_require_connected_ai(auth_client, db_session):
    from datetime import UTC, datetime

    from app.models.app_setting import AppSetting

    for key, value in {
        "license_tier": "pro",
        "license_status": "active",
        "license_verified_at": datetime.now(UTC).isoformat(),
    }.items():
        db_session.query(AppSetting).filter_by(key=key).one().value = value
    db_session.commit()

    insights = auth_client.post(
        '/api/v1/reports/ai/insights',
        json={'month': '2025-01', 'consent': True},
    )
    detailed_pdf = auth_client.post(
        '/api/v1/reports/pdf/detailed',
        json={'month': '2025-01', 'consent': True},
    )
    assert insights.status_code == 409
    assert detailed_pdf.status_code == 409
    assert "Connect an AI" in insights.json()["detail"]


def test_hosted_reports_require_saved_provider_disclosure_consent(
    auth_client,
    db_session,
):
    from datetime import UTC, datetime

    from app.models.app_setting import AppSetting

    for key, value in {
        "license_tier": "pro",
        "license_status": "active",
        "license_verified_at": datetime.now(UTC).isoformat(),
    }.items():
        db_session.query(AppSetting).filter_by(key=key).one().value = value
    db_session.add(
        LLMConfiguration(
            provider="openai",
            auth_method="openapi",
            model="gpt-test",
            is_active=True,
        )
    )
    db_session.commit()

    response = auth_client.post(
        "/api/v1/reports/ai/insights",
        json={"month": "2025-01", "consent": True},
    )
    assert response.status_code == 409
    assert "data disclosure" in response.json()["detail"]


def test_detailed_reports_never_mislabel_a_rules_fallback_as_ai(
    auth_client,
    db_session,
    monkeypatch,
):
    from datetime import UTC, datetime

    from app.models.app_setting import AppSetting

    for key, value in {
        "license_tier": "pro",
        "license_status": "active",
        "license_verified_at": datetime.now(UTC).isoformat(),
    }.items():
        db_session.query(AppSetting).filter_by(key=key).one().value = value
    _activate_test_llm(db_session)
    _add_txn(
        db_session,
        "SALARY",
        75000,
        date(2025, 1, 1),
        category="INCOME",
        txn_type="credit",
    )
    db_session.commit()

    def unavailable(*args, **kwargs):
        raise RuntimeError("model is offline")

    monkeypatch.setattr("app.core.reporting.call_llm", unavailable)
    response = auth_client.post(
        '/api/v1/reports/ai/insights',
        json={'month': '2025-01', 'consent': True},
    )
    assert response.status_code == 502
    assert "did not return a usable report" in response.json()["detail"]


def test_summary_pdf_endpoint(auth_client, db_session, monkeypatch):
    _add_txn(
        db_session,
        'SALARY',
        75000,
        date(2025, 1, 1),
        category='INCOME',
        txn_type='credit',
    )
    db_session.commit()

    def forbidden_ai_call(*_args, **_kwargs):
        raise AssertionError('standard summary must never call an LLM')

    monkeypatch.setattr('app.core.reporting.call_llm', forbidden_ai_call)
    resp = auth_client.get('/api/v1/reports/pdf/summary?month=2025-01')
    assert resp.status_code == 200
    assert resp.headers['content-type'] == 'application/pdf'
    assert len(resp.content) > 100
    # PDF magic bytes
    assert resp.content[:5] == b'%PDF-'


def test_ai_report_requires_explicit_consent(auth_client, db_session, monkeypatch):
    from datetime import UTC, datetime

    from app.models.app_setting import AppSetting

    for key, value in {
        'license_tier': 'pro',
        'license_status': 'active',
        'license_verified_at': datetime.now(UTC).isoformat(),
    }.items():
        db_session.query(AppSetting).filter_by(key=key).one().value = value
    _activate_test_llm(db_session)
    calls = []
    monkeypatch.setattr(
        'app.core.reporting.call_llm',
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    insights = auth_client.post(
        '/api/v1/reports/ai/insights',
        json={'month': '2025-01', 'consent': False},
    )
    detailed_pdf = auth_client.post(
        '/api/v1/reports/pdf/detailed',
        json={'month': '2025-01', 'consent': False},
    )

    assert insights.status_code == 400
    assert detailed_pdf.status_code == 400
    assert calls == []


def test_detailed_pdf_endpoint(auth_client, db_session, monkeypatch):
    from datetime import UTC, datetime

    from app.models.app_setting import AppSetting

    for key, value in {
        "license_tier": "pro",
        "license_status": "active",
        "license_verified_at": datetime.now(UTC).isoformat(),
    }.items():
        db_session.query(AppSetting).filter_by(key=key).one().value = value
    _activate_test_llm(db_session)
    _add_txn(
        db_session,
        "SALARY",
        75000,
        date(2025, 1, 1),
        category="INCOME",
        txn_type="credit",
    )
    db_session.commit()
    monkeypatch.setattr(
        "app.core.reporting.call_llm",
        lambda *args, **kwargs: _valid_llm_report(),
    )
    resp = auth_client.post(
        '/api/v1/reports/pdf/detailed',
        json={'month': '2025-01', 'consent': True},
    )
    assert resp.status_code == 200
    assert resp.headers['content-type'] == 'application/pdf'
    assert len(resp.content) > 100
    # PDF magic bytes
    assert resp.content[:5] == b'%PDF-'
    with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
        pdf_text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    assert 'AI REPORT DISCLOSURE' in pdf_text
    assert 'ollama_local / qwen-test' in pdf_text
    assert 'Data provided to the connected AI' in pdf_text


def test_csv_endpoint(auth_client):
    resp = auth_client.get('/api/v1/reports/csv?month=2025-01')
    assert resp.status_code == 200
    assert resp.headers['content-type'].startswith('text/csv')
    content = resp.content.decode('utf-8')
    assert 'Date,M' in content  # Header row starts with Date


def test_report_default_month(auth_client):
    # No month param — should default to current month
    resp = auth_client.get('/api/v1/reports/summary')
    assert resp.status_code == 200
    data = resp.json()
    assert 'month' in data
