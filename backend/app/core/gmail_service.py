"""Gmail API service with OAuth flow state management."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parseaddr
from email.mime.text import MIMEText
import hashlib
import hmac
import json
import logging
import os
from pathlib import Path
import secrets
import stat
import tempfile
from typing import Iterator, Optional
from urllib.parse import urlparse

from google.auth.exceptions import RefreshError, TransportError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from sqlalchemy.orm import Session

from app.core.encryption import EncryptionError, decrypt, encrypt
from app.core.local_api_trust import mint_oauth_callback_state
from app.models.gmail_oauth_attempt import GmailOAuthAttempt
from app.models.session import AuthSession

logger = logging.getLogger(__name__)

SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
]

GMAIL_READONLY_SCOPE = SCOPES[0]
GMAIL_SEND_SCOPE = 'https://www.googleapis.com/auth/gmail.send'
OAUTH_ATTEMPT_TTL_SECONDS = 10 * 60
OAUTH_REDIRECT_URI = os.environ.get(
    "GODFIN_GMAIL_REDIRECT_URI",
    "http://127.0.0.1:5100/api/v1/auth/gmail/callback",
)
SUPPORTED_SENDER_ADDRESSES = {
    "alerts@hdfcbank.net",
    "alerts@hdfcbank.bank.in",
}

# Client secrets - load from environment variable or file (file should NOT be in repo)
# Format for env var: GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET (JSON format)
CLIENT_SECRETS_FILE = Path(
    os.environ.get(
        "GODFIN_GMAIL_CLIENT_SECRETS_FILE",
        Path(__file__).parent.parent.parent / "data" / "client_secret.json",
    )
).expanduser()

# Token storage path (for persisting credentials)
TOKEN_FILE = Path(
    os.environ.get(
        "GODFIN_GMAIL_TOKEN_FILE",
        Path(__file__).parent.parent.parent / "data" / "gmail_token.json",
    )
).expanduser()
MAX_TOKEN_FILE_BYTES = 64 * 1024


class GmailError(RuntimeError):
    """Base error with stable machine-readable sync/auth semantics."""

    def __init__(self, message: str, *, code: str, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class GmailConfigurationError(GmailError):
    pass


class GmailOAuthStateError(GmailError):
    pass


class GmailSyncError(GmailError):
    pass


@dataclass(frozen=True)
class GmailFetchResult:
    messages: list[dict]
    history_id: Optional[str]
    status: str = "complete"
    errors: tuple[str, ...] = field(default_factory=tuple)
    retryable: bool = False

    def __iter__(self) -> Iterator[object]:
        """Preserve the historical ``messages, history_id = ...`` contract."""
        yield self.messages
        yield self.history_id


@dataclass(frozen=True)
class GmailConnectionHealth:
    status: str
    connected: bool
    message: str
    retryable: bool = False
    action_required: str | None = None
    credentials_present: bool = False
    token_expiry: str | None = None
    last_refresh_success_at: str | None = None
    last_refresh_failure_at: str | None = None
    client_config_match: bool | None = None
    safe_reason_code: str = "not_connected"

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "connected": self.connected,
            "message": self.message,
            "retryable": self.retryable,
            "action_required": self.action_required,
            "credentials_present": self.credentials_present,
            "token_expiry": self.token_expiry,
            "last_refresh_success_at": self.last_refresh_success_at,
            "last_refresh_failure_at": self.last_refresh_failure_at,
            "client_config_match": self.client_config_match,
            "safe_reason_code": self.safe_reason_code,
        }


@dataclass(frozen=True)
class GmailDisconnectOutcome:
    """Support-safe result for local credential removal and remote revocation."""

    local_credentials_removed: bool
    remote_revocation_status: str
    safe_reason_code: str

    @property
    def remote_revocation_pending(self) -> bool:
        return self.remote_revocation_status == "unconfirmed"

    def __bool__(self) -> bool:
        return self.local_credentials_removed


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _credentials_expiry_from_storage(value: str | None) -> datetime | None:
    """Return the naive-UTC expiry representation required by google-auth."""
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _credentials_expiry_for_storage(value: datetime | None) -> str | None:
    """Persist an unambiguous UTC timestamp without changing the instant."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat().replace("+00:00", "Z")


def _read_token_data() -> dict:
    metadata = TOKEN_FILE.lstat()
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError("Stored Gmail permission is not a regular file.")
    if metadata.st_size > MAX_TOKEN_FILE_BYTES:
        raise ValueError("Stored Gmail permission is unexpectedly large.")
    os.chmod(TOKEN_FILE, 0o600)
    with open(TOKEN_FILE, "r", encoding="utf-8") as handle:
        token_data = json.load(handle)
    if not isinstance(token_data, dict):
        raise ValueError("Stored Gmail permission is not an object.")
    return token_data


def _write_token_data(token_data: dict) -> None:
    payload = json.dumps(token_data, separators=(",", ":"))
    if len(payload.encode("utf-8")) > MAX_TOKEN_FILE_BYTES:
        raise ValueError("Stored Gmail permission is unexpectedly large.")
    if TOKEN_FILE.is_symlink() or TOKEN_FILE.parent.is_symlink():
        raise OSError("Gmail permission path cannot be a symbolic link.")
    parent_existed = TOKEN_FILE.parent.exists()
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not parent_existed:
        os.chmod(TOKEN_FILE.parent, 0o700)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".gmail-token-",
        suffix=".json",
        dir=TOKEN_FILE.parent,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, TOKEN_FILE)
        os.chmod(TOKEN_FILE, 0o600)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def _remove_local_token_file() -> None:
    """Remove only the configured token directory entry, never a symlink target."""

    try:
        metadata = TOKEN_FILE.lstat()
    except FileNotFoundError:
        return
    if not (stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode)):
        raise OSError("Gmail permission path is not a removable credential file.")
    TOKEN_FILE.unlink()


def _state_hash(state: str) -> str:
    return hashlib.sha256(state.encode("utf-8")).hexdigest()


def _is_loopback_redirect(uri: str) -> bool:
    parsed = urlparse(uri)
    return (
        parsed.scheme == "http"
        and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        and parsed.port is not None
        and parsed.path == "/api/v1/auth/gmail/callback"
        and not parsed.username
        and not parsed.password
        and not parsed.query
        and not parsed.fragment
    )


def _validate_client_config(config: object) -> dict:
    if not isinstance(config, dict):
        raise GmailConfigurationError(
            "The Gmail connection file is not valid JSON configuration.",
            code="invalid_client_config",
        )
    installed = config.get("installed")
    if not isinstance(installed, dict):
        raise GmailConfigurationError(
            "GODFIN requires a dedicated Google OAuth Desktop app connection.",
            code="desktop_client_required",
        )
    if not installed.get("client_id") or not installed.get("client_secret"):
        raise GmailConfigurationError(
            "The Gmail connection file is missing its desktop client details.",
            code="incomplete_client_config",
        )
    return config


def _load_client_config() -> Optional[dict]:
    """Load and validate the dedicated installed-app client configuration."""
    # First try environment variable
    client_id = os.environ.get('GOOGLE_CLIENT_ID')
    client_secret = os.environ.get('GOOGLE_CLIENT_SECRET')

    if client_id and client_secret:
        return _validate_client_config({
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"],
            }
        })

    # Fall back to file (user must provide this)
    if CLIENT_SECRETS_FILE.exists():
        try:
            with open(CLIENT_SECRETS_FILE, 'r', encoding="utf-8") as f:
                return _validate_client_config(json.load(f))
        except json.JSONDecodeError as exc:
            raise GmailConfigurationError(
                "The Gmail connection file is not valid JSON.",
                code="invalid_client_config",
            ) from exc

    return None


def _client_config_fingerprint(config: dict | None) -> str | None:
    installed = config.get("installed") if isinstance(config, dict) else None
    client_id = installed.get("client_id") if isinstance(installed, dict) else None
    if not isinstance(client_id, str) or not client_id:
        return None
    return hashlib.sha256(client_id.encode("utf-8")).hexdigest()


def _stored_client_fingerprint(token_data: dict) -> str | None:
    fingerprint = token_data.get("client_config_fingerprint")
    if isinstance(fingerprint, str) and len(fingerprint) == 64:
        try:
            bytes.fromhex(fingerprint)
            return fingerprint
        except ValueError:
            return None
    client_id = token_data.get("client_id")
    if isinstance(client_id, str) and client_id:
        return hashlib.sha256(client_id.encode("utf-8")).hexdigest()
    return None


def _safe_token_health_metadata() -> dict[str, object]:
    if not TOKEN_FILE.exists():
        return {
            "credentials_present": False,
            "token_expiry": None,
            "last_refresh_success_at": None,
            "last_refresh_failure_at": None,
            "client_config_match": None,
        }
    try:
        token_data = _read_token_data()
        expiry = _credentials_expiry_for_storage(
            _credentials_expiry_from_storage(token_data.get("expiry"))
        )
        current = _client_config_fingerprint(_load_client_config())
        stored = _stored_client_fingerprint(token_data)
        return {
            "credentials_present": True,
            "token_expiry": expiry,
            "last_refresh_success_at": token_data.get("last_refresh_success_at"),
            "last_refresh_failure_at": token_data.get("last_refresh_failure_at"),
            "client_config_match": (
                secrets.compare_digest(current, stored)
                if current is not None and stored is not None
                else None
            ),
        }
    except (GmailConfigurationError, json.JSONDecodeError, OSError, TypeError, ValueError):
        return {
            "credentials_present": True,
            "token_expiry": None,
            "last_refresh_success_at": None,
            "last_refresh_failure_at": None,
            "client_config_match": None,
        }


def _record_token_diagnostic(**updates: str | None) -> None:
    try:
        token_data = _read_token_data()
        token_data.update(updates)
        _write_token_data(token_data)
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        logger.warning("Gmail diagnostic state could not be persisted")


def client_config_available() -> bool:
    """Return whether this build has a desktop Gmail connection configured."""
    try:
        return _load_client_config() is not None
    except GmailConfigurationError:
        return False


class GmailService:
    """Manages Gmail API connection and OAuth flow state."""

    def __init__(self):
        self._credentials = None
        self.service = None
        self._connection_health = GmailConnectionHealth(
            status="not_connected",
            connected=False,
            message="Connect Gmail to import transaction alerts.",
            action_required="connect",
        )

    def _set_connection_health(
        self,
        *,
        status: str,
        connected: bool,
        message: str,
        retryable: bool = False,
        action_required: str | None = None,
        safe_reason_code: str | None = None,
    ) -> None:
        metadata = _safe_token_health_metadata()
        self._connection_health = GmailConnectionHealth(
            status=status,
            connected=connected,
            message=message,
            retryable=retryable,
            action_required=action_required,
            credentials_present=bool(metadata["credentials_present"]),
            token_expiry=metadata["token_expiry"],
            last_refresh_success_at=metadata["last_refresh_success_at"],
            last_refresh_failure_at=metadata["last_refresh_failure_at"],
            client_config_match=metadata["client_config_match"],
            safe_reason_code=safe_reason_code or status,
        )

    def connection_health(self) -> GmailConnectionHealth:
        """Return a safe, actionable state without exposing provider details."""
        if (
            self._connection_health.action_required == "reconnect"
            and self._connection_health.status
            in {"reauthorization_required", "client_config_changed", "credential_corrupt"}
        ):
            return self._connection_health
        if self._credentials is not None and self._credentials.valid:
            self._set_connection_health(
                status="connected",
                connected=True,
                message="Gmail permission is active.",
                safe_reason_code="connected",
            )
        elif TOKEN_FILE.exists():
            self.load_credentials()
        elif not client_config_available():
            self._set_connection_health(
                status="not_configured",
                connected=False,
                message=(
                    "Gmail connection is not configured for this GODFIN build yet."
                ),
                action_required="owner_configuration",
                safe_reason_code="client_config_missing",
            )
        else:
            self._set_connection_health(
                status="ready",
                connected=False,
                message="Gmail is ready to connect.",
                action_required="connect",
                safe_reason_code="not_connected",
            )
        return self._connection_health

    def _authorization_required(self) -> GmailSyncError:
        self._credentials = None
        self.service = None
        self._set_connection_health(
            status="reauthorization_required",
            connected=False,
            message="Google no longer accepts this Gmail permission. Connect Gmail again.",
            action_required="reconnect",
            safe_reason_code="provider_permission_rejected",
        )
        return GmailSyncError(
            "Gmail permission expired. Connect Gmail again.",
            code="authorization_required",
        )

    def get_auth_url(
        self,
        db: Session,
        *,
        session_token_hash: str,
        redirect_uri: str = OAUTH_REDIRECT_URI,
    ) -> str:
        """Create a persisted, session-bound installed-app OAuth attempt."""
        if not _is_loopback_redirect(redirect_uri):
            raise GmailConfigurationError(
                "Gmail authorization must return to the local GODFIN app.",
                code="invalid_redirect_uri",
            )
        client_config = _load_client_config()
        if not client_config:
            raise GmailConfigurationError(
                "Gmail connection is not configured for this GODFIN build yet.",
                code="client_config_missing",
            )

        launch_secret = os.environ.get("GODFIN_LAUNCH_SECRET")
        state = (
            mint_oauth_callback_state(launch_secret)
            if launch_secret
            else secrets.token_urlsafe(32)
        )
        code_verifier = secrets.token_urlsafe(64)
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode("ascii")).digest()
        ).rstrip(b"=").decode("ascii")

        flow = Flow.from_client_config(
            client_config,
            scopes=SCOPES,
            redirect_uri=redirect_uri,
        )

        now = _utcnow_naive()
        db.query(GmailOAuthAttempt).filter(
            GmailOAuthAttempt.expires_at <= now,
        ).delete(synchronize_session=False)
        db.add(
            GmailOAuthAttempt(
                state_hash=_state_hash(state),
                session_token_hash=session_token_hash,
                code_verifier_encrypted=encrypt(code_verifier),
                redirect_uri=redirect_uri,
                created_at=now,
                expires_at=now + timedelta(seconds=OAUTH_ATTEMPT_TTL_SECONDS),
            )
        )
        db.commit()

        auth_url, _ = flow.authorization_url(
            access_type="offline",
            prompt="consent",
            include_granted_scopes="true",
            state=state,
            code_challenge=code_challenge,
            code_challenge_method="S256",
        )
        logger.info("Generated a session-bound Gmail OAuth URL")
        return auth_url

    def _consume_oauth_attempt(
        self,
        db: Session,
        *,
        state: str,
        redirect_uri: str,
    ) -> str:
        if not state:
            raise GmailOAuthStateError(
                "The Gmail approval response did not include its security state.",
                code="missing_state",
            )
        if not _is_loopback_redirect(redirect_uri):
            raise GmailOAuthStateError(
                "The Gmail approval returned to an unexpected address.",
                code="redirect_mismatch",
            )

        digest = _state_hash(state)
        attempt = db.query(GmailOAuthAttempt).filter_by(state_hash=digest).first()
        if attempt is None or not hmac.compare_digest(attempt.state_hash, digest):
            raise GmailOAuthStateError(
                "This Gmail approval was not started by the current GODFIN app.",
                code="invalid_state",
            )
        if attempt.redirect_uri != redirect_uri:
            raise GmailOAuthStateError(
                "The Gmail approval returned to an unexpected address.",
                code="redirect_mismatch",
            )

        now = _utcnow_naive()
        if attempt.consumed_at is not None:
            raise GmailOAuthStateError(
                "This Gmail approval was already used. Start a new connection.",
                code="replayed_state",
            )
        if attempt.expires_at <= now:
            attempt.consumed_at = now
            db.commit()
            raise GmailOAuthStateError(
                "This Gmail approval expired. Start the connection again.",
                code="expired_state",
            )
        session = db.query(AuthSession).filter(
            AuthSession.token_hash == attempt.session_token_hash,
            AuthSession.expires_at > now,
        ).first()
        if session is None:
            attempt.consumed_at = now
            db.commit()
            raise GmailOAuthStateError(
                "The GODFIN session that started this approval expired. Unlock and try again.",
                code="initiating_session_expired",
            )

        encrypted_verifier = attempt.code_verifier_encrypted
        updated = (
            db.query(GmailOAuthAttempt)
            .filter(
                GmailOAuthAttempt.id == attempt.id,
                GmailOAuthAttempt.consumed_at.is_(None),
                GmailOAuthAttempt.expires_at > now,
            )
            .update({GmailOAuthAttempt.consumed_at: now}, synchronize_session=False)
        )
        if updated != 1:
            db.rollback()
            raise GmailOAuthStateError(
                "This Gmail approval was already used. Start a new connection.",
                code="replayed_state",
            )
        db.commit()
        return decrypt(encrypted_verifier)

    def cancel_auth(
        self,
        db: Session,
        *,
        state: str,
        redirect_uri: str = OAUTH_REDIRECT_URI,
    ) -> None:
        """Validate and consume a provider-cancelled OAuth attempt."""
        self._consume_oauth_attempt(db, state=state, redirect_uri=redirect_uri)

    def complete_auth(
        self,
        db: Session,
        *,
        authorization_code: str,
        state: str,
        redirect_uri: str = OAUTH_REDIRECT_URI,
    ) -> bool:
        """Validate one-time state and exchange the loopback authorization code."""
        code_verifier = self._consume_oauth_attempt(
            db,
            state=state,
            redirect_uri=redirect_uri,
        )
        client_config = _load_client_config()
        if not client_config:
            raise GmailConfigurationError(
                "Gmail connection is not configured for this GODFIN build yet.",
                code="client_config_missing",
            )

        try:
            flow = Flow.from_client_config(
                client_config,
                scopes=SCOPES,
                redirect_uri=redirect_uri,
            )
            flow.fetch_token(
                code=authorization_code,
                code_verifier=code_verifier,
            )
            self._credentials = flow.credentials
            self._persist_credentials(refresh_succeeded=True)
            self._build_service()
            self._set_connection_health(
                status="connected",
                connected=True,
                message="Gmail permission is active.",
                safe_reason_code="connected",
            )
            logger.info("Gmail authentication completed successfully")
            return True
        except GmailError:
            raise
        except Exception as exc:
            logger.warning("Gmail token exchange failed")
            raise GmailError(
                "Google could not finish the Gmail connection. Start again.",
                code="token_exchange_failed",
                retryable=False,
            ) from exc

    def _persist_credentials(self, *, refresh_succeeded: bool = False) -> None:
        if self._credentials is None:
            raise GmailError(
                "No Gmail credentials are available to save.",
                code="credentials_missing",
            )
        previous: dict = {}
        if TOKEN_FILE.exists():
            try:
                previous = _read_token_data()
            except (json.JSONDecodeError, OSError, TypeError, ValueError):
                previous = {}
        now = _utcnow_naive().replace(tzinfo=timezone.utc).isoformat().replace(
            "+00:00", "Z"
        )
        current_config = _load_client_config()
        credential_client_id = self._credentials.client_id or ""
        client_config_fingerprint = _client_config_fingerprint(current_config)
        if client_config_fingerprint is None and credential_client_id:
            client_config_fingerprint = hashlib.sha256(
                credential_client_id.encode("utf-8")
            ).hexdigest()
        if client_config_fingerprint is None:
            raise GmailError(
                "Gmail credentials do not identify an OAuth client.",
                code="client_identity_missing",
            )
        token_data = {
            'token': encrypt(self._credentials.token) if self._credentials.token else None,
            'refresh_token': encrypt(self._credentials.refresh_token) if self._credentials.refresh_token else None,
            'token_uri': self._credentials.token_uri,
            'client_id': self._credentials.client_id,
            'client_secret': encrypt(self._credentials.client_secret) if self._credentials.client_secret else None,
            'scopes': list(self._credentials.scopes) if self._credentials.scopes else [],
            'expiry': _credentials_expiry_for_storage(
                self._credentials.expiry
            ),
            'client_config_fingerprint': client_config_fingerprint,
            'last_refresh_success_at': (
                now if refresh_succeeded else previous.get('last_refresh_success_at')
            ),
            'last_refresh_failure_at': previous.get('last_refresh_failure_at'),
            'safe_reason_code': 'connected',
        }
        _write_token_data(token_data)

    def load_credentials(self) -> bool:
        """Load saved credentials from disk."""
        if (
            self._connection_health.action_required == "reconnect"
            and self._connection_health.status
            in {"reauthorization_required", "client_config_changed", "credential_corrupt"}
        ):
            return False
        if not TOKEN_FILE.exists():
            self._credentials = None
            self.service = None
            self._set_connection_health(
                status="not_connected",
                connected=False,
                message="Connect Gmail to import transaction alerts.",
                action_required="connect",
                safe_reason_code="not_connected",
            )
            return False

        try:
            token_data = _read_token_data()

            current_config = _load_client_config()
            current_fingerprint = _client_config_fingerprint(current_config)
            stored_fingerprint = _stored_client_fingerprint(token_data)
            if current_fingerprint is None:
                self._credentials = None
                self.service = None
                self._set_connection_health(
                    status="not_configured",
                    connected=False,
                    message="Gmail connection is not configured for this GODFIN build yet.",
                    action_required="owner_configuration",
                    safe_reason_code="client_config_missing",
                )
                return False
            if (
                stored_fingerprint is None
                or not secrets.compare_digest(current_fingerprint, stored_fingerprint)
            ):
                self._credentials = None
                self.service = None
                self._set_connection_health(
                    status="client_config_changed",
                    connected=False,
                    message=(
                        "GODFIN's Google connection changed after Gmail was approved. "
                        "Connect Gmail again; previously imported transactions stay here."
                    ),
                    action_required="reconnect",
                    safe_reason_code="oauth_client_changed",
                )
                return False

            parsed_expiry = _credentials_expiry_from_storage(
                token_data.get('expiry')
            )

            # Decrypt sensitive fields
            self._credentials = Credentials(
                token=decrypt(token_data.get('token')) if token_data.get('token') else None,
                refresh_token=decrypt(token_data.get('refresh_token')) if token_data.get('refresh_token') else None,
                token_uri=token_data.get('token_uri'),
                client_id=token_data.get('client_id'),
                client_secret=decrypt(token_data.get('client_secret')) if token_data.get('client_secret') else None,
                scopes=token_data.get('scopes'),
                expiry=parsed_expiry,
            )

            if self._credentials.expired:
                if not self._credentials.refresh_token:
                    _record_token_diagnostic(
                        last_refresh_failure_at=_utcnow_naive()
                        .replace(tzinfo=timezone.utc)
                        .isoformat()
                        .replace("+00:00", "Z"),
                        safe_reason_code="refresh_token_missing",
                    )
                    self._credentials = None
                    self.service = None
                    self._set_connection_health(
                        status="reauthorization_required",
                        connected=False,
                        message="Gmail permission expired. Connect Gmail again.",
                        action_required="reconnect",
                        safe_reason_code="refresh_token_missing",
                    )
                    return False
                try:
                    self._set_connection_health(
                        status="refreshing",
                        connected=False,
                        message="GODFIN is checking the saved Gmail permission.",
                        retryable=True,
                        action_required="retry",
                        safe_reason_code="refreshing",
                    )
                    self._credentials.refresh(Request())
                    self._persist_credentials(refresh_succeeded=True)
                except RefreshError:
                    logger.info("Gmail authorization is no longer valid")
                    _remove_local_token_file()
                    self._credentials = None
                    self.service = None
                    self._set_connection_health(
                        status="reauthorization_required",
                        connected=False,
                        message="Google no longer accepts this Gmail permission. Connect Gmail again.",
                        action_required="reconnect",
                        safe_reason_code="refresh_token_rejected",
                    )
                    return False
                except TransportError:
                    logger.info("Gmail credential refresh is temporarily unavailable")
                    _record_token_diagnostic(
                        last_refresh_failure_at=_utcnow_naive()
                        .replace(tzinfo=timezone.utc)
                        .isoformat()
                        .replace("+00:00", "Z"),
                        safe_reason_code="google_temporarily_unreachable",
                    )
                    self._credentials = None
                    self.service = None
                    self._set_connection_health(
                        status="temporarily_unavailable",
                        connected=False,
                        message="Google could not be reached. GODFIN will not sync until a retry succeeds.",
                        retryable=True,
                        action_required="retry",
                        safe_reason_code="google_temporarily_unreachable",
                    )
                    return False

            if not self._credentials.valid:
                _record_token_diagnostic(
                    last_refresh_failure_at=_utcnow_naive()
                    .replace(tzinfo=timezone.utc)
                    .isoformat()
                    .replace("+00:00", "Z"),
                    safe_reason_code="credential_incomplete",
                )
                self._credentials = None
                self.service = None
                self._set_connection_health(
                    status="reauthorization_required",
                    connected=False,
                    message="Gmail permission is incomplete. Connect Gmail again.",
                    action_required="reconnect",
                    safe_reason_code="credential_incomplete",
                )
                return False

            self._build_service()
            self._set_connection_health(
                status="connected",
                connected=True,
                message="Gmail permission is active.",
                safe_reason_code="connected",
            )
            return True
        except (EncryptionError, json.JSONDecodeError, OSError, TypeError, ValueError):
            logger.warning("Stored Gmail credentials could not be loaded")
            self._credentials = None
            self.service = None
            self._set_connection_health(
                status="credential_corrupt",
                connected=False,
                message="Stored Gmail permission is unreadable. Connect Gmail again.",
                action_required="reconnect",
                safe_reason_code="credential_unreadable",
            )
            return False
        except Exception:
            logger.exception("Unexpected Gmail credential loading failure")
            self._credentials = None
            self.service = None
            self._set_connection_health(
                status="credential_corrupt",
                connected=False,
                message="Gmail permission could not be checked safely. Connect Gmail again.",
                action_required="reconnect",
                safe_reason_code="credential_load_failed",
            )
            return False

    def _build_service(self):
        """Build Gmail API service from credentials."""
        if self._credentials:
            self.service = build(
                'gmail',
                'v1',
                credentials=self._credentials,
                cache_discovery=False,
            )

    @property
    def is_connected(self) -> bool:
        """Check if Gmail is connected and authenticated."""
        try:
            if self._credentials is None:
                self.load_credentials()
            connected = self._credentials is not None and self._credentials.valid
            if connected:
                self._set_connection_health(
                    status="connected",
                    connected=True,
                    message="Gmail permission is active.",
                    safe_reason_code="connected",
                )
            return connected
        except Exception:
            logger.warning("Gmail connection state could not be checked")
            self._set_connection_health(
                status="credential_corrupt",
                connected=False,
                message="Gmail permission could not be checked safely. Connect Gmail again.",
                action_required="reconnect",
                safe_reason_code="credential_check_failed",
            )
            return False

    def get_user_email(self) -> Optional[str]:
        """Get the authenticated user's email address."""
        if not self.service:
            if not self.load_credentials():
                return None
        try:
            profile = self.service.users().getProfile(userId="me").execute()
            return profile.get("emailAddress")
        except Exception as e:
            logger.error(f"Error getting user email: {e}")
            return None

    @property
    def can_send(self) -> bool:
        scopes = set(self._credentials.scopes or []) if self._credentials else set()
        return GMAIL_SEND_SCOPE in scopes

    def send_email(self, to_email: str, subject: str, html: str) -> bool:
        """Send an opt-in message directly through the user's Gmail account."""
        if not self.service and not self.load_credentials():
            raise RuntimeError("Connect Gmail before enabling weekly digest delivery.")
        if not self.can_send:
            raise RuntimeError(
                "Gmail was connected before digest email permission was added. "
                "Reconnect Gmail to enable weekly digest delivery."
            )
        sender = self.get_user_email()
        if not sender:
            raise RuntimeError("Could not determine the connected Gmail address.")
        message = MIMEText(html, "html", "utf-8")
        message["to"] = to_email
        message["from"] = sender
        message["subject"] = subject
        payload = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
        self.service.users().messages().send(
            userId="me", body={"raw": payload}
        ).execute()
        return True

    def disconnect(self) -> GmailDisconnectOutcome:
        """Remove local credentials and report remote revocation separately."""
        remote_revocation_status = "not_required"
        try:
            if self._credentials:
                # Remote revocation is best-effort. Local credential removal must still
                # complete when Google is temporarily unavailable.
                import requests
                revocation_token = (
                    self._credentials.refresh_token or self._credentials.token
                )
                remote_revocation_status = "unconfirmed"
                try:
                    response = requests.post(
                        'https://oauth2.googleapis.com/revoke',
                        params={'token': revocation_token},
                        headers={'content-type': 'application/x-www-form-urlencoded'},
                        timeout=10,
                    )
                    if response.status_code == 200:
                        remote_revocation_status = "revoked"
                    else:
                        logger.warning(
                            "Gmail token revocation was not confirmed (HTTP %s)",
                            response.status_code,
                        )
                except Exception as e:
                    logger.warning(
                        "Gmail token revocation could not be confirmed: %s",
                        type(e).__name__,
                    )

            self._credentials = None
            self.service = None
            if TOKEN_FILE.exists():
                TOKEN_FILE.unlink()
            self._set_connection_health(
                status="not_connected",
                connected=False,
                message="Gmail is disconnected.",
                action_required="connect",
            )
            return GmailDisconnectOutcome(
                local_credentials_removed=True,
                remote_revocation_status=remote_revocation_status,
                safe_reason_code=(
                    "remote_revocation_unconfirmed"
                    if remote_revocation_status == "unconfirmed"
                    else "credentials_removed"
                ),
            )
        except Exception as e:
            logger.error("Failed to remove Gmail credentials: %s", type(e).__name__)
            return GmailDisconnectOutcome(
                local_credentials_removed=False,
                remote_revocation_status=remote_revocation_status,
                safe_reason_code="local_credential_removal_failed",
            )

    def fetch_messages(self, history_id: Optional[str] = None, max_results: int = 100,
                       after_date: Optional[str] = None,
                       before_date: Optional[str] = None) -> GmailFetchResult:
        """Fetch Gmail messages with pagination and a durable high-water cursor.

        Args:
            history_id: Gmail history cursor for incremental sync.
            max_results: Maximum messages to fetch across all pages.
            after_date: RFC 3339 date (YYYY-MM-DD) for filtering (inclusive)
            before_date: RFC 3339 date (YYYY-MM-DD) for filtering (exclusive)
        """
        if max_results < 1:
            raise ValueError("max_results must be at least 1")
        if not self.service and not self.load_credentials():
            health = self._connection_health
            if health.retryable:
                raise GmailSyncError(
                    health.message,
                    code="provider_failure",
                    retryable=True,
                )
            if health.action_required == "reconnect":
                raise GmailSyncError(
                    health.message,
                    code="authorization_required",
                )
            raise GmailSyncError(
                "Connect Gmail before importing email transactions.",
                code="not_connected",
            )

        query_parts = ['from:(alerts@hdfcbank.net OR alerts@hdfcbank.bank.in)']
        if after_date:
            query_parts.append(f'after:{after_date}')
        if before_date:
            query_parts.append(f'before:{before_date}')
        query = ' '.join(query_parts)

        message_ids: list[str] = []
        seen_ids: set[str] = set()
        errors: list[str] = []
        new_history_id: Optional[str] = None
        stopped_at_limit = False

        try:
            if history_id:
                page_token = None
                while len(message_ids) < max_results:
                    try:
                        request = self.service.users().history().list(
                            userId='me',
                            startHistoryId=history_id,
                            historyTypes=['messageAdded'],
                            maxResults=min(500, max_results - len(message_ids)),
                            pageToken=page_token,
                        )
                        response = request.execute()
                    except HttpError as exc:
                        status = getattr(exc.resp, 'status', None)
                        if status in {401, 403}:
                            raise self._authorization_required() from exc
                        if status == 404:
                            raise GmailSyncError(
                                "Gmail's saved sync position expired; a safe full rescan is required.",
                                code="history_expired",
                            ) from exc
                        if not message_ids:
                            raise GmailSyncError(
                                "Gmail could not provide new-message history.",
                                code="provider_failure",
                                retryable=status in {408, 429, 500, 502, 503, 504},
                            ) from exc
                        errors.append("Gmail history pagination stopped before all pages were read.")
                        break
                    except Exception as exc:
                        if not message_ids:
                            raise GmailSyncError(
                                "Gmail could not provide new-message history.",
                                code="provider_failure",
                                retryable=True,
                            ) from exc
                        errors.append("Gmail history pagination stopped before all pages were read.")
                        break

                    for record in response.get('history', []):
                        for added in record.get('messagesAdded', []):
                            message_id = added.get('message', {}).get('id')
                            if message_id and message_id not in seen_ids:
                                seen_ids.add(message_id)
                                message_ids.append(message_id)
                                if len(message_ids) >= max_results:
                                    break
                        if len(message_ids) >= max_results:
                            break
                    new_history_id = response.get('historyId') or new_history_id
                    page_token = response.get('nextPageToken')
                    if page_token and len(message_ids) >= max_results:
                        stopped_at_limit = True
                    if not page_token:
                        break
            else:
                try:
                    profile = self.service.users().getProfile(userId='me').execute()
                    new_history_id = profile.get('historyId')
                except HttpError as exc:
                    status = getattr(exc.resp, 'status', None)
                    if status in {401, 403}:
                        raise self._authorization_required() from exc
                    errors.append("Gmail did not provide a durable sync position.")
                except Exception:
                    errors.append("Gmail did not provide a durable sync position.")

                page_token = None
                while len(message_ids) < max_results:
                    try:
                        response = self.service.users().messages().list(
                            userId='me',
                            q=query,
                            maxResults=min(500, max_results - len(message_ids)),
                            pageToken=page_token,
                        ).execute()
                    except HttpError as exc:
                        status = getattr(exc.resp, 'status', None)
                        if status in {401, 403}:
                            raise self._authorization_required() from exc
                        if not message_ids:
                            raise GmailSyncError(
                                "Gmail could not list transaction emails.",
                                code="provider_failure",
                                retryable=status in {408, 429, 500, 502, 503, 504},
                            ) from exc
                        errors.append("Gmail message pagination stopped before all pages were read.")
                        break
                    except Exception as exc:
                        if not message_ids:
                            raise GmailSyncError(
                                "Gmail could not list transaction emails.",
                                code="provider_failure",
                                retryable=True,
                            ) from exc
                        errors.append("Gmail message pagination stopped before all pages were read.")
                        break

                    for metadata in response.get('messages', []):
                        message_id = metadata.get('id')
                        if message_id and message_id not in seen_ids:
                            seen_ids.add(message_id)
                            message_ids.append(message_id)
                            if len(message_ids) >= max_results:
                                break
                    page_token = response.get('nextPageToken')
                    if page_token and len(message_ids) >= max_results:
                        stopped_at_limit = True
                    if not page_token:
                        break
        except GmailSyncError:
            raise

        if stopped_at_limit:
            errors.append(
                "Gmail has more matching messages than this safe sync can process at once. "
                "Use a narrower date range; the saved sync position was not advanced."
            )

        messages: list[dict] = []
        retryable_partial = stopped_at_limit
        for message_id in message_ids:
            try:
                message = self._get_message(message_id)
            except HttpError as exc:
                status = getattr(exc.resp, 'status', None)
                if status in {401, 403}:
                    raise self._authorization_required() from exc
                retryable_partial = retryable_partial or status in {
                    408, 429, 500, 502, 503, 504
                }
                errors.append(f"Message {message_id} could not be read.")
                continue
            except Exception:
                retryable_partial = True
                errors.append(f"Message {message_id} could not be read.")
                continue

            if history_id:
                sender_address = parseaddr(message.get('sender', ''))[1].lower()
                if sender_address not in SUPPORTED_SENDER_ADDRESSES:
                    continue
            messages.append(message)

        if errors:
            return GmailFetchResult(
                messages=messages,
                history_id=None,
                status="partial",
                errors=tuple(errors[:10]),
                retryable=retryable_partial,
            )
        return GmailFetchResult(
            messages=messages,
            history_id=new_history_id,
            status="empty" if not messages else "complete",
        )

    def _get_message(self, msg_id: str) -> dict:
        msg = self.service.users().messages().get(
            userId='me', id=msg_id, format='full'
        ).execute()

        headers = {
            h.get('name', ''): h.get('value', '')
            for h in msg.get('payload', {}).get('headers', [])
            if isinstance(h, dict)
        }
        sender = headers.get('From', '')
        subject = headers.get('Subject', '')
        date_str = headers.get('Date', '')
        internal_date = msg.get('internalDate')
        body = self._extract_body(msg.get('payload', {}))

        return {
            'id': msg_id,
            'thread_id': msg.get('threadId', ''),
            'sender': sender,
            'subject': subject,
            'date': date_str,
            'internal_date': int(internal_date) if internal_date else None,
            'body': body,
            'historyId': msg.get('historyId'),
        }

    def _extract_body(self, payload: dict) -> str:
        """Extract body from message payload."""
        import re

        def get_body_from_parts(parts):
            for part in parts:
                mime_type = part.get('mimeType', '')

                # Prefer text/plain
                if mime_type == 'text/plain':
                    data = part.get('body', {}).get('data', '')
                    if data:
                        return base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')

                # Check nested parts
                if 'parts' in part:
                    result = get_body_from_parts(part['parts'])
                    if result:
                        return result

            # Fallback to text/html
            for part in parts:
                if part.get('mimeType') == 'text/html':
                    data = part.get('body', {}).get('data', '')
                    if data:
                        html = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
                        text = re.sub(r'<[^>]+>', ' ', html)
                        text = re.sub(r'\s+', ' ', text)
                        return text

            return ""

        if 'parts' in payload:
            return get_body_from_parts(payload['parts'])
        elif payload.get('mimeType') == 'text/plain':
            data = payload.get('body', {}).get('data', '')
            if data:
                return base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
        elif payload.get('mimeType') == 'text/html':
            data = payload.get('body', {}).get('data', '')
            if data:
                html = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
                text = re.sub(r'<[^>]+>', ' ', html)
                text = re.sub(r'\s+', ' ', text)
                return text

        return ""


# Singleton instance
gmail_service = GmailService()


def get_credentials() -> Optional[Credentials]:
    """Get credentials (backward compatible)."""
    return gmail_service._credentials if gmail_service.is_connected else None


def is_connected() -> bool:
    """Check if connected (backward compatible)."""
    return gmail_service.is_connected


def get_gmail_service():
    """Get Gmail service (backward compatible)."""
    if not gmail_service.is_connected:
        return None
    return gmail_service.service


def fetch_messages(history_id: Optional[str] = None, max_results: int = 100,
                   after_date: Optional[str] = None,
                   before_date: Optional[str] = None) -> GmailFetchResult:
    """Fetch messages through the process-local Gmail service instance."""
    return gmail_service.fetch_messages(history_id, max_results, after_date, before_date)
