from __future__ import annotations

import os
import tempfile
import uuid
from datetime import date

from app.models.app_setting import AppSetting
from app.models.transaction import Transaction
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
    db.flush()
    return txn


# --- Settings Endpoints ---

def test_list_settings(auth_client):
    resp = auth_client.get('/api/v1/settings')
    assert resp.status_code == 200
    data = resp.json()
    assert 'user_timezone' in data
    assert 'developer_mode' in data
    assert 'backup_directory' in data
    assert 'pin_hash' not in data
    assert 'is_first_run' not in data
    assert 'license_key' not in data
    assert 'license_tier' not in data
    assert 'license_status' not in data
    assert 'schema_revision' not in data


def test_update_timezone(auth_client):
    resp = auth_client.put(
        '/api/v1/settings/preferences/timezone',
        json={'timezone': 'US/Eastern'},
    )
    assert resp.status_code == 200
    assert resp.json()['value'] == 'US/Eastern'


def test_update_timezone_rejects_unknown_zone(auth_client):
    resp = auth_client.put(
        '/api/v1/settings/preferences/timezone',
        json={'timezone': 'Definitely/Not-A-Timezone'},
    )
    assert resp.status_code == 422


def test_generic_setting_mutation_is_deny_by_default(auth_client, db_session):
    protected = {
        'pin_hash': 'hacked',
        'pin_length': '8',
        'is_first_run': 'true',
        'license_key': 'forged-key',
        'license_tier': 'max',
        'license_status': 'active',
        'license_last_verified': '2099-01-01T00:00:00Z',
        'license_device_id': 'attacker-device',
        'schema_revision': '999',
        'migration_version': '999',
        'encryption_key': 'attacker-controlled-key',
        'encryption_key_version': '999',
        'allow_network_access': 'true',
        'developer_mode': 'true',
        'enable_embeddings': 'true',
        'does_not_exist': 'test',
    }
    before = {
        key: (
            db_session.query(AppSetting).filter_by(key=key).first().value
            if db_session.query(AppSetting).filter_by(key=key).first()
            else None
        )
        for key in protected
    }

    for key, value in protected.items():
        resp = auth_client.put(f'/api/v1/settings/{key}', json={'value': value})
        assert resp.status_code == 403, key

    db_session.expire_all()
    for key in protected:
        setting = db_session.query(AppSetting).filter_by(key=key).first()
        assert (setting.value if setting else None) == before[key]


def test_settings_health_card_payload(auth_client):
    resp = auth_client.get('/api/v1/settings/health')
    assert resp.status_code == 200
    data = resp.json()
    assert set(data) == {
        'encryption', 'gmail', 'llm', 'backup', 'ingestion', 'network',
        'license',
    }
    assert data['encryption']['status'] == 'ok'
    assert data['network']['allow_network_access'] is False


def test_settings_health_surfaces_persistent_backup_degradation(
    auth_client,
    db_session,
):
    values = {
        "backup_scheduler_status": "degraded",
        "backup_scheduler_failure_code": "scheduler_start_failed",
        "backup_scheduler_last_failure_at": "2026-08-11T01:00:00+00:00",
        "backup_scheduler_next_retry_at": "2026-08-11T01:01:00+00:00",
        "backup_scheduler_failure_count": "2",
        "backup_last_success_at": "2026-08-10T18:29:00+00:00",
    }
    for key, value in values.items():
        db_session.merge(AppSetting(key=key, value=value))
    db_session.commit()

    backup = auth_client.get('/api/v1/settings/health').json()['backup']

    assert backup['status'] == 'degraded'
    assert backup['scheduler_status'] == 'degraded'
    assert backup['failure_code'] == 'scheduler_start_failed'
    assert backup['failure_count'] == 2
    assert backup['last_success_at'] == '2026-08-10T18:29:00+00:00'
    assert backup['next_retry_at'] == '2026-08-11T01:01:00+00:00'
    assert 'retry automatically' in backup['message'].lower()


def test_network_access_toggle_requires_restart(auth_client):
    resp = auth_client.put(
        '/api/v1/settings/preferences/network-access',
        json={'enabled': True, 'current_pin': '4826'},
    )
    assert resp.status_code == 200
    assert resp.json()['restart_required'] is True

    health = auth_client.get('/api/v1/settings/health').json()
    assert health['network']['allow_network_access'] is True


def test_network_access_enable_requires_current_pin(auth_client):
    missing = auth_client.put(
        '/api/v1/settings/preferences/network-access',
        json={'enabled': True},
    )
    wrong = auth_client.put(
        '/api/v1/settings/preferences/network-access',
        json={'enabled': True, 'current_pin': '9999'},
    )

    assert missing.status_code == 403
    assert wrong.status_code == 403


def test_developer_mode_enable_requires_current_pin(auth_client):
    missing = auth_client.put(
        '/api/v1/settings/preferences/developer-mode',
        json={'enabled': True},
    )
    accepted = auth_client.put(
        '/api/v1/settings/preferences/developer-mode',
        json={'enabled': True, 'current_pin': '4826'},
    )

    assert missing.status_code == 403
    assert accepted.status_code == 200
    assert accepted.json()['value'] == 'true'


# --- Developer Mode ---

def test_developer_mode_status(auth_client):
    resp = auth_client.get('/api/v1/settings/developer')
    assert resp.status_code == 200
    data = resp.json()
    assert 'developer_mode' in data
    assert 'rules' in data
    assert isinstance(data['rules'], list)


# --- CSV Export ---

def test_csv_export_empty(auth_client):
    resp = auth_client.get('/api/v1/reports/csv?month=2020-01')
    assert resp.status_code == 200
    assert resp.headers['content-type'] == 'text/csv; charset=utf-8'
    content = resp.text
    lines = content.strip().split('\n')
    assert len(lines) == 1  # Header only
    assert 'Date' in lines[0]
    assert 'Amount' in lines[0]


def test_csv_export_with_data(auth_client, db_session):
    _add_txn(db_session, 'SWIGGY', 500, date(2025, 6, 5), category='FOOD & DINING')
    _add_txn(db_session, 'SALARY', 75000, date(2025, 6, 1), category='INCOME', txn_type='credit')
    _add_txn(db_session, 'RENT', 20000, date(2025, 6, 3), category='HOUSING')
    db_session.commit()

    resp = auth_client.get('/api/v1/reports/csv?month=2025-06')
    assert resp.status_code == 200
    content = resp.text.strip()
    lines = [l for l in content.split('\n') if l.strip()]
    assert len(lines) >= 3  # Header + at least 2 transactions
    assert 'SWIGGY' in content
    assert 'RENT' in content


# --- Backup (unit tests) ---

def test_create_and_list_backups():
    from app.core.backup import create_backup, list_backups

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a dummy source DB
        import sqlite3
        src_path = os.path.join(tmpdir, 'test.db')
        conn = sqlite3.connect(src_path)
        conn.execute('CREATE TABLE test (id INTEGER)')
        conn.close()

        backup_dir = os.path.join(tmpdir, 'backups')
        filename = create_backup(src_path, backup_dir)

        assert filename.startswith('godfin_backup_')
        assert filename.endswith('.db')

        backups = list_backups(backup_dir)
        assert len(backups) == 1
        assert backups[0]['filename'] == filename
        assert backups[0]['size_bytes'] > 0


def test_list_backups_empty():
    from app.core.backup import list_backups

    with tempfile.TemporaryDirectory() as tmpdir:
        backups = list_backups(os.path.join(tmpdir, 'nonexistent'))
        assert backups == []


# --- Data Reset ---

def test_reset_data_success(auth_client, db_session, monkeypatch):
    # Add some data
    _add_txn(db_session, 'SWIGGY', 500, date(2025, 6, 5), category='FOOD & DINING')
    db_session.commit()

    # Backups are covered with a real temporary SQLite file above; this API
    # fixture uses a shared in-memory database and must not touch the user's DB.
    monkeypatch.setattr(
        "app.api.v1.endpoints.settings.create_backup",
        lambda *_args, **_kwargs: "godfin_backup_test.db",
    )
    resp = auth_client.post('/api/v1/settings/reset-data', json={'pin': '4826'})
    assert resp.status_code == 200
    data = resp.json()
    assert data['success'] is True
    assert data['backup_created'] is True
    assert data['backup_filename'] == "godfin_backup_test.db"
    assert 'All data has been reset' in data['message']

    # Verify transactions are gone
    db_session.expire_all()
    assert db_session.query(Transaction).count() == 0


def test_reset_data_wrong_pin(auth_client):
    resp = auth_client.post('/api/v1/settings/reset-data', json={'pin': '0000'})
    assert resp.status_code == 403
    assert resp.json()['detail'] == 'Incorrect PIN'
    # A wrong destructive-action confirmation is not an expired login session.
    assert auth_client.get('/api/v1/settings').status_code == 200
