from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest
from google.auth.exceptions import RefreshError, TransportError
from googleapiclient.errors import HttpError

from app.core import gmail_service as gmail_module
from app.core.encryption import encrypt
from app.core.gmail_service import (
    GMAIL_READONLY_SCOPE,
    GmailFetchResult,
    GmailOAuthStateError,
    GmailService,
    GmailSyncError,
    OAUTH_REDIRECT_URI,
    SCOPES,
)
from app.models.gmail_oauth_attempt import GmailOAuthAttempt
from app.models.session import AuthSession


CLIENT_CONFIG = {
    "installed": {
        "client_id": "test-client.apps.googleusercontent.com",
        "client_secret": "test-secret",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost"],
    }
}


class FakeCredentials:
    token = "access-token"
    refresh_token = "refresh-token"
    token_uri = "https://oauth2.googleapis.com/token"
    client_id = "test-client.apps.googleusercontent.com"
    client_secret = "test-secret"
    scopes = [GMAIL_READONLY_SCOPE]
    expiry = datetime.now(timezone.utc) + timedelta(hours=1)
    expired = False
    valid = True


class FakeFlow:
    instances = []

    def __init__(self, redirect_uri):
        self.redirect_uri = redirect_uri
        self.authorization_kwargs = None
        self.fetch_kwargs = None
        self.credentials = FakeCredentials()
        self.__class__.instances.append(self)

    def authorization_url(self, **kwargs):
        self.authorization_kwargs = kwargs
        return (
            "https://accounts.google.com/o/oauth2/auth?state=" + kwargs["state"],
            kwargs["state"],
        )

    def fetch_token(self, **kwargs):
        self.fetch_kwargs = kwargs


@pytest.fixture
def fake_oauth(monkeypatch, tmp_path):
    FakeFlow.instances.clear()
    monkeypatch.setattr(gmail_module, "_load_client_config", lambda: CLIENT_CONFIG)
    monkeypatch.setattr(
        gmail_module.Flow,
        "from_client_config",
        lambda config, scopes, redirect_uri: FakeFlow(redirect_uri),
    )
    monkeypatch.setattr(gmail_module, "TOKEN_FILE", tmp_path / "gmail_token.json")


def test_gmail_scope_is_readonly_only():
    assert SCOPES == [GMAIL_READONLY_SCOPE]


def test_oauth_attempt_is_hashed_bound_expiring_and_pkce(
    db_session,
    fake_oauth,
):
    service = GmailService()
    auth_url = service.get_auth_url(
        db_session,
        session_token_hash="a" * 64,
    )

    state = parse_qs(urlparse(auth_url).query)["state"][0]
    attempt = db_session.query(GmailOAuthAttempt).one()
    assert attempt.state_hash == hashlib.sha256(state.encode()).hexdigest()
    assert state not in attempt.state_hash
    assert attempt.session_token_hash == "a" * 64
    assert attempt.redirect_uri == OAUTH_REDIRECT_URI
    assert attempt.expires_at > attempt.created_at
    assert attempt.expires_at - attempt.created_at == timedelta(minutes=10)

    kwargs = FakeFlow.instances[-1].authorization_kwargs
    assert kwargs["state"] == state
    assert kwargs["code_challenge_method"] == "S256"
    assert kwargs["code_challenge"]
    assert kwargs["access_type"] == "offline"


def test_concurrent_oauth_attempts_do_not_overwrite_each_other(
    db_session,
    fake_oauth,
):
    service = GmailService()
    first = service.get_auth_url(db_session, session_token_hash="a" * 64)
    second = service.get_auth_url(db_session, session_token_hash="b" * 64)

    assert first != second
    attempts = db_session.query(GmailOAuthAttempt).all()
    assert len(attempts) == 2
    assert len({attempt.state_hash for attempt in attempts}) == 2
    assert len({attempt.code_verifier_encrypted for attempt in attempts}) == 2


def _add_attempt(db_session, state: str, *, expires_delta=timedelta(minutes=5)):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    session = db_session.query(AuthSession).filter_by(token_hash="a" * 64).first()
    if session is None:
        db_session.add(
            AuthSession(
                token_hash="a" * 64,
                created_at=now,
                last_seen_at=now,
                expires_at=now + timedelta(hours=1),
            )
        )
    attempt = GmailOAuthAttempt(
        state_hash=hashlib.sha256(state.encode()).hexdigest(),
        session_token_hash="a" * 64,
        code_verifier_encrypted=encrypt("pkce-verifier"),
        redirect_uri=OAUTH_REDIRECT_URI,
        created_at=now,
        expires_at=now + expires_delta,
    )
    db_session.add(attempt)
    db_session.commit()
    return attempt


def test_oauth_callback_consumes_state_once_and_persists_credentials(
    db_session,
    fake_oauth,
    monkeypatch,
):
    state = "valid-state"
    _add_attempt(db_session, state)
    service = GmailService()
    monkeypatch.setattr(service, "_build_service", lambda: None)

    assert service.complete_auth(
        db_session,
        authorization_code="provider-code",
        state=state,
    )
    assert gmail_module.TOKEN_FILE.exists()
    assert gmail_module.TOKEN_FILE.stat().st_mode & 0o077 == 0
    assert FakeFlow.instances[-1].fetch_kwargs == {
        "code": "provider-code",
        "code_verifier": "pkce-verifier",
    }

    with pytest.raises(GmailOAuthStateError) as replay:
        service.complete_auth(
            db_session,
            authorization_code="provider-code",
            state=state,
        )
    assert replay.value.code == "replayed_state"


@pytest.mark.parametrize(
    ("state", "expected_code"),
    [("", "missing_state"), ("wrong-state", "invalid_state")],
)
def test_oauth_callback_rejects_missing_or_wrong_state(
    db_session,
    fake_oauth,
    state,
    expected_code,
):
    service = GmailService()
    with pytest.raises(GmailOAuthStateError) as error:
        service.complete_auth(
            db_session,
            authorization_code="provider-code",
            state=state,
        )
    assert error.value.code == expected_code
    assert not gmail_module.TOKEN_FILE.exists()


def test_oauth_callback_rejects_expired_and_altered_redirect(
    db_session,
    fake_oauth,
):
    _add_attempt(db_session, "expired", expires_delta=timedelta(seconds=-1))
    service = GmailService()
    with pytest.raises(GmailOAuthStateError) as expired:
        service.complete_auth(
            db_session,
            authorization_code="provider-code",
            state="expired",
        )
    assert expired.value.code == "expired_state"

    _add_attempt(db_session, "redirect")
    with pytest.raises(GmailOAuthStateError) as redirect:
        service.complete_auth(
            db_session,
            authorization_code="provider-code",
            state="redirect",
            redirect_uri="http://127.0.0.1:5999/api/v1/auth/gmail/callback",
        )
    assert redirect.value.code == "redirect_mismatch"


class ResultRequest:
    def __init__(self, value):
        self.value = value

    def execute(self):
        if isinstance(self.value, Exception):
            raise self.value
        return self.value


def _message_payload(message_id, sender="alerts@hdfcbank.net"):
    return {
        "id": message_id,
        "threadId": "thread-" + message_id,
        "historyId": "900",
        "internalDate": "1700000000000",
        "payload": {
            "headers": [
                {"name": "From", "value": sender},
                {"name": "Subject", "value": "Transaction alert"},
            ],
            "mimeType": "text/plain",
            "body": {"data": "VGVzdCBib2R5"},
        },
    }


class FakeMessagesApi:
    def __init__(self, pages, messages):
        self.pages = pages
        self.messages = messages
        self.list_calls = []

    def list(self, **kwargs):
        self.list_calls.append(kwargs)
        token = kwargs.get("pageToken")
        return ResultRequest(self.pages[token])

    def get(self, **kwargs):
        return ResultRequest(self.messages[kwargs["id"]])


class FakeHistoryApi:
    def __init__(self, pages):
        self.pages = pages
        self.list_calls = []

    def list(self, **kwargs):
        self.list_calls.append(kwargs)
        token = kwargs.get("pageToken")
        return ResultRequest(self.pages[token])


class FakeUsersApi:
    def __init__(self, message_pages, messages, history_pages=None, profile=None):
        self.messages_api = FakeMessagesApi(message_pages, messages)
        self.history_api = FakeHistoryApi(history_pages or {})
        self.profile = profile or {"historyId": "profile-1000"}

    def messages(self):
        return self.messages_api

    def history(self):
        return self.history_api

    def getProfile(self, **kwargs):
        return ResultRequest(self.profile)


class FakeGmailApi:
    def __init__(self, users):
        self.users_api = users

    def users(self):
        return self.users_api


def test_message_listing_paginates_with_gmail_page_limit():
    ids = [f"m{i}" for i in range(501)]
    pages = {
        None: {
            "messages": [{"id": message_id} for message_id in ids[:500]],
            "nextPageToken": "page-2",
        },
        "page-2": {"messages": [{"id": ids[500]}]},
    }
    users = FakeUsersApi(
        pages,
        {message_id: _message_payload(message_id) for message_id in ids},
    )
    service = GmailService()
    service.service = FakeGmailApi(users)

    result = service.fetch_messages(max_results=1000)

    assert isinstance(result, GmailFetchResult)
    assert len(result.messages) == 501
    assert result.history_id == "profile-1000"
    assert result.status == "complete"
    assert [call["maxResults"] for call in users.messages_api.list_calls] == [500, 500]


def test_history_listing_paginates_deduplicates_and_filters_sender():
    pages = {
        None: {
            "history": [
                {"messagesAdded": [{"message": {"id": "bank-1"}}]},
                {"messagesAdded": [{"message": {"id": "duplicate"}}]},
            ],
            "historyId": "901",
            "nextPageToken": "next",
        },
        "next": {
            "history": [
                {"messagesAdded": [{"message": {"id": "duplicate"}}]},
                {"messagesAdded": [{"message": {"id": "other"}}]},
            ],
            "historyId": "902",
        },
    }
    users = FakeUsersApi(
        {},
        {
            "bank-1": _message_payload("bank-1"),
            "duplicate": _message_payload("duplicate"),
            "other": _message_payload("other", sender="person@example.com"),
        },
        history_pages=pages,
    )
    service = GmailService()
    service.service = FakeGmailApi(users)

    result = service.fetch_messages(history_id="900", max_results=100)

    assert [message["id"] for message in result.messages] == ["bank-1", "duplicate"]
    assert result.history_id == "902"
    assert len(users.history_api.list_calls) == 2


def test_provider_failure_is_not_reported_as_empty_mailbox():
    users = FakeUsersApi(
        {None: RuntimeError("network down")},
        {},
        profile={"historyId": "1000"},
    )
    service = GmailService()
    service.service = FakeGmailApi(users)

    with pytest.raises(GmailSyncError) as error:
        service.fetch_messages(max_results=100)
    assert error.value.code == "provider_failure"
    assert error.value.retryable is True


def test_partial_message_failure_keeps_messages_but_not_cursor():
    pages = {None: {"messages": [{"id": "good"}, {"id": "bad"}]}}
    users = FakeUsersApi(
        pages,
        {
            "good": _message_payload("good"),
            "bad": RuntimeError("temporary read failure"),
        },
    )
    service = GmailService()
    service.service = FakeGmailApi(users)

    result = service.fetch_messages(max_results=100)

    assert [message["id"] for message in result.messages] == ["good"]
    assert result.status == "partial"
    assert result.history_id is None
    assert result.retryable is True


def test_expired_history_cursor_has_explicit_failure():
    not_found = HttpError(
        resp=SimpleNamespace(status=404, reason="Not Found"),
        content=b'{"error":{"message":"History ID not found"}}',
    )
    users = FakeUsersApi({}, {}, history_pages={None: not_found})
    service = GmailService()
    service.service = FakeGmailApi(users)

    with pytest.raises(GmailSyncError) as error:
        service.fetch_messages(history_id="expired", max_results=100)
    assert error.value.code == "history_expired"


@pytest.mark.parametrize(
    ("refresh_error", "expected_status", "retryable", "action"),
    [
        (RefreshError("invalid_grant"), "reauthorize", False, "reconnect"),
        (TransportError("network unavailable"), "temporarily_unavailable", True, "retry"),
    ],
)
def test_expired_credential_status_distinguishes_reauth_from_retry(
    fake_oauth,
    monkeypatch,
    refresh_error,
    expected_status,
    retryable,
    action,
):
    class ExpiredCredentials:
        expired = True
        valid = False
        refresh_token = "encrypted-refresh-token"

        def refresh(self, _request):
            raise refresh_error

    gmail_module.TOKEN_FILE.write_text(
        json.dumps(
            {
                "token": "encrypted-access-token",
                "refresh_token": "encrypted-refresh-token",
                "token_uri": "https://oauth2.googleapis.com/token",
                "client_id": "test-client.apps.googleusercontent.com",
                "client_secret": "encrypted-client-secret",
                "scopes": [GMAIL_READONLY_SCOPE],
                "expiry": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(gmail_module, "decrypt", lambda value: value)
    monkeypatch.setattr(
        gmail_module,
        "Credentials",
        lambda **_kwargs: ExpiredCredentials(),
    )

    service = GmailService()

    assert service.load_credentials() is False
    health = service.connection_health()
    assert health.status == expected_status
    assert health.connected is False
    assert health.retryable is retryable
    assert health.action_required == action


def test_message_limit_is_partial_and_never_advances_cursor():
    ids = ["m1", "m2"]
    pages = {
        None: {
            "messages": [{"id": message_id} for message_id in ids],
            "nextPageToken": "more-messages",
        },
        "more-messages": {"messages": [{"id": "m3"}]},
    }
    users = FakeUsersApi(
        pages,
        {message_id: _message_payload(message_id) for message_id in ids},
    )
    service = GmailService()
    service.service = FakeGmailApi(users)

    result = service.fetch_messages(max_results=2)

    assert [message["id"] for message in result.messages] == ids
    assert result.status == "partial"
    assert result.history_id is None
    assert result.retryable is True
    assert "narrower date range" in result.errors[0].lower()
    assert len(users.messages_api.list_calls) == 1


def test_history_limit_is_partial_and_never_advances_cursor():
    pages = {
        None: {
            "history": [
                {"messagesAdded": [{"message": {"id": "m1"}}]},
                {"messagesAdded": [{"message": {"id": "m2"}}]},
            ],
            "historyId": "901",
            "nextPageToken": "more-history",
        },
        "more-history": {
            "history": [
                {"messagesAdded": [{"message": {"id": "m3"}}]},
            ],
            "historyId": "902",
        },
    }
    users = FakeUsersApi(
        {},
        {
            "m1": _message_payload("m1"),
            "m2": _message_payload("m2"),
        },
        history_pages=pages,
    )
    service = GmailService()
    service.service = FakeGmailApi(users)

    result = service.fetch_messages(history_id="900", max_results=2)

    assert [message["id"] for message in result.messages] == ["m1", "m2"]
    assert result.status == "partial"
    assert result.history_id is None
    assert result.retryable is True
    assert len(users.history_api.list_calls) == 1


def test_revoked_provider_permission_requires_reauthorization():
    unauthorized = HttpError(
        resp=SimpleNamespace(status=401, reason="Unauthorized"),
        content=b'{"error":{"message":"Invalid Credentials"}}',
    )
    users = FakeUsersApi(
        {None: unauthorized},
        {},
        profile={"historyId": "1000"},
    )
    service = GmailService()
    service.service = FakeGmailApi(users)

    with pytest.raises(GmailSyncError) as error:
        service.fetch_messages(max_results=100)

    assert error.value.code == "authorization_required"
    assert error.value.retryable is False
    health = service.connection_health()
    assert health.status == "reauthorize"
    assert health.action_required == "reconnect"
