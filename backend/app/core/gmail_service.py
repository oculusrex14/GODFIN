"""Gmail API service with OAuth flow state management."""

from __future__ import annotations

import base64
from email.mime.text import MIMEText
import json
import logging
import os
from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from app.core.encryption import encrypt, decrypt

logger = logging.getLogger(__name__)

SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send',
]

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


def _load_client_config() -> dict:
    """Load client configuration from environment or file."""
    # First try environment variable
    client_id = os.environ.get('GOOGLE_CLIENT_ID')
    client_secret = os.environ.get('GOOGLE_CLIENT_SECRET')

    if client_id and client_secret:
        return {
            "web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uris": ["http://localhost:5100/api/v1/auth/gmail/callback"],
                "javascript_origins": ["http://localhost:5100", "http://localhost:5200"]
            }
        }

    # Fall back to file (user must provide this)
    if CLIENT_SECRETS_FILE.exists():
        with open(CLIENT_SECRETS_FILE, 'r') as f:
            return json.load(f)

    return None


class GmailService:
    """Manages Gmail API connection and OAuth flow state."""

    def __init__(self):
        self._flow = None  # Store flow for PKCE
        self._redirect_uri = None  # Store redirect URI for callback
        self._credentials = None
        self._state = None  # Store state for CSRF protection
        self._code_verifier = None  # Store PKCE code verifier
        self.service = None

    def get_auth_url(self, redirect_uri: str = None, use_oob: bool = False) -> Optional[str]:
        """Generate OAuth authorization URL for Gmail access.

        Args:
            redirect_uri: The URI to redirect to after auth. If not provided,
                          uses localhost as fallback.
            use_oob: If True, use out-of-band flow (manual code entry).
                     Useful for mobile/network access where redirect URIs
                     with private IPs are not allowed by Google.
        """
        import secrets as random_secrets
        import hashlib
        import base64
        client_config = _load_client_config()
        if not client_config:
            logger.error("Client secrets not found. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET environment variables or provide client_secret.json")
            return None

        # For out-of-band flow, PKCE is not supported
        if use_oob:
            self._redirect_uri = "urn:ietf:wg:oauth:2.0:oob"
            self._code_verifier = None
        else:
            self._redirect_uri = redirect_uri or "http://localhost:5100/api/v1/auth/gmail/callback"
            # Generate PKCE code verifier and challenge
            self._code_verifier = random_secrets.token_urlsafe(32)
            # Create code challenge from verifier (S256 method)
            code_challenge = base64.urlsafe_b64encode(
                hashlib.sha256(self._code_verifier.encode()).digest()
            ).rstrip(b'=').decode()

        logger.info(f"Using redirect_uri: {self._redirect_uri}")

        # Use Flow instead of InstalledAppFlow to have more control
        self._flow = Flow.from_client_config(
            client_config,
            scopes=SCOPES,
            redirect_uri=self._redirect_uri
        )

        # Generate state parameter for CSRF protection
        self._state = random_secrets.token_urlsafe(32)

        # Build authorization URL with PKCE if available
        auth_params = {
            'access_type': 'offline',
            'prompt': 'consent',
            'state': self._state,
        }
        if self._code_verifier:
            auth_params['code_challenge'] = code_challenge
            auth_params['code_challenge_method'] = 'S256'

        auth_url, _ = self._flow.authorization_url(**auth_params)
        logger.info(f"Generated auth_url with PKCE: {auth_url[:100]}...")
        return auth_url

    def complete_auth(self, authorization_code: str, redirect_uri: str = None) -> bool:
        """Complete OAuth flow with authorization code.

        Args:
            authorization_code: The code returned by Google OAuth
            redirect_uri: The redirect URI used in the auth request
        """
        try:
            # Use provided redirect_uri or stored one or default
            redirect_uri = redirect_uri or self._redirect_uri or "http://localhost:5100/api/v1/auth/gmail/callback"

            if self._flow is None or self._redirect_uri != redirect_uri:
                # If flow is None (server restart) or redirect_uri changed, create a new one
                logger.info("Creating new flow for token exchange")
                client_config = _load_client_config()
                if not client_config:
                    logger.error("Client secrets not found")
                    return False
                self._flow = Flow.from_client_config(
                    client_config,
                    scopes=SCOPES,
                    redirect_uri=redirect_uri
                )
                self._redirect_uri = redirect_uri

            # Fetch token using the same flow instance
            # Pass code_verifier for PKCE (required when code_challenge was sent)
            if self._code_verifier:
                self._flow.fetch_token(code=authorization_code, code_verifier=self._code_verifier)
            else:
                self._flow.fetch_token(code=authorization_code)
            self._credentials = self._flow.credentials

            # Save token for future use (encrypt sensitive fields)
            token_data = {
                'token': encrypt(self._credentials.token) if self._credentials.token else None,
                'refresh_token': encrypt(self._credentials.refresh_token) if self._credentials.refresh_token else None,
                'token_uri': self._credentials.token_uri,
                'client_id': self._credentials.client_id,
                'client_secret': encrypt(self._credentials.client_secret) if self._credentials.client_secret else None,
                'scopes': list(self._credentials.scopes) if self._credentials.scopes else [],
            }
            TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(TOKEN_FILE, "w") as f:
                json.dump(token_data, f)
            os.chmod(TOKEN_FILE, 0o600)

            self._build_service()
            logger.info("Gmail authentication completed successfully")
            return True
        except Exception as e:
            logger.error(f"Auth error: {e}")
            return False

    def load_credentials(self) -> bool:
        """Load saved credentials from disk."""
        if not TOKEN_FILE.exists():
            return False

        try:
            with open(TOKEN_FILE, "r") as f:
                token_data = json.load(f)

            # Decrypt sensitive fields
            self._credentials = Credentials(
                token=decrypt(token_data.get('token')) if token_data.get('token') else None,
                refresh_token=decrypt(token_data.get('refresh_token')) if token_data.get('refresh_token') else None,
                token_uri=token_data.get('token_uri'),
                client_id=token_data.get('client_id'),
                client_secret=decrypt(token_data.get('client_secret')) if token_data.get('client_secret') else None,
                scopes=token_data.get('scopes'),
            )

            # Refresh if expired
            if self._credentials.expired and self._credentials.refresh_token:
                try:
                    self._credentials.refresh(Request())
                    # Re-encrypt the new token
                    token_data['token'] = encrypt(self._credentials.token)
                    with open(TOKEN_FILE, "w") as f:
                        json.dump(token_data, f)
                    os.chmod(TOKEN_FILE, 0o600)
                except Exception as e:
                    logger.warning(f"Failed to refresh credentials: {e}")
                    return False

            self._build_service()
            return True
        except Exception as e:
            logger.error(f"Error loading credentials: {e}")
            return False

    def _build_service(self):
        """Build Gmail API service from credentials."""
        if self._credentials:
            self.service = build('gmail', 'v1', credentials=self._credentials)

    @property
    def is_connected(self) -> bool:
        """Check if Gmail is connected and authenticated."""
        try:
            if self._credentials is None:
                self.load_credentials()
            return self._credentials is not None and self._credentials.valid
        except Exception as e:
            logger.warning(f"Error checking is_connected: {e}")
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
        return "https://www.googleapis.com/auth/gmail.send" in scopes

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

    def disconnect(self) -> bool:
        """Remove stored credentials."""
        try:
            if self._credentials:
                # Try to revoke the token
                import requests
                try:
                    requests.post(
                        'https://oauth2.googleapis.com/revoke',
                        params={'token': self._credentials.token},
                        headers={'content-type': 'application/x-www-form-urlencoded'}
                    )
                except Exception as e:
                    logger.warning(f"Failed to revoke token: {e}")

            self._credentials = None
            self.service = None
            self._flow = None
            self._redirect_uri = None

            if TOKEN_FILE.exists():
                TOKEN_FILE.unlink()
            return True
        except Exception as e:
            logger.error(f"Failed to disconnect: {e}")
            return False

    def fetch_messages(self, history_id: Optional[str] = None, max_results: int = 100,
                       after_date: Optional[str] = None, before_date: Optional[str] = None):
        """
        Fetch messages from Gmail.

        Args:
            history_id: For incremental sync (optional)
            max_results: Maximum messages to fetch
            after_date: RFC 3339 date (YYYY-MM-DD) for filtering (inclusive)
            before_date: RFC 3339 date (YYYY-MM-DD) for filtering (exclusive)
        """
        if not self.service:
            raise RuntimeError("Gmail service not initialized. Complete auth first.")

        messages = []

        # Build query for HDFC Bank senders
        query_parts = ['from:(alerts@hdfcbank.net OR alerts@hdfcbank.bank.in)']
        if after_date:
            query_parts.append(f'after:{after_date}')
        if before_date:
            query_parts.append(f'before:{before_date}')

        query = ' '.join(query_parts)

        try:
            response = self.service.users().messages().list(
                userId='me',
                q=query,
                maxResults=max_results,
            ).execute()

            new_history_id = None

            for msg_meta in response.get('messages', []):
                msg = self._get_message(msg_meta['id'])
                if msg:
                    messages.append(msg)
                    if not new_history_id and msg.get('historyId'):
                        new_history_id = msg['historyId']

            return messages, new_history_id

        except Exception as e:
            logger.error(f"Gmail fetch error: {e}")
            return [], None

    def _get_message(self, msg_id: str) -> Optional[dict]:
        try:
            msg = self.service.users().messages().get(
                userId='me', id=msg_id, format='full'
            ).execute()

            headers = {h['name']: h['value'] for h in msg.get('payload', {}).get('headers', [])}
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
        except Exception as e:
            logger.error(f"Failed to get message {msg_id}: {e}")
            return None

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


# Backward compatibility functions
def get_oauth_url() -> Optional[str]:
    """Get OAuth URL (backward compatible)."""
    return gmail_service.get_auth_url()


def handle_oauth_callback(code: str) -> bool:
    """Handle OAuth callback (backward compatible)."""
    return gmail_service.complete_auth(code)


def handle_manual_oauth_code(code: str) -> tuple[bool, str]:
    """Handle manual OAuth code entry."""
    success = gmail_service.complete_auth(code)
    if success:
        return True, "Gmail connected successfully"
    else:
        return False, "Failed to authenticate with Gmail"


def get_credentials() -> Optional[Credentials]:
    """Get credentials (backward compatible)."""
    return gmail_service._credentials if gmail_service.is_connected else None


def is_connected() -> bool:
    """Check if connected (backward compatible)."""
    return gmail_service.is_connected


def disconnect_gmail() -> bool:
    """Disconnect Gmail (backward compatible)."""
    return gmail_service.disconnect()


def get_gmail_service():
    """Get Gmail service (backward compatible)."""
    if not gmail_service.is_connected:
        return None
    return gmail_service.service


def fetch_messages(history_id: Optional[str] = None, max_results: int = 100,
                   after_date: Optional[str] = None, before_date: Optional[str] = None):
    """Fetch messages (backward compatible)."""
    if not gmail_service.is_connected:
        return [], None
    return gmail_service.fetch_messages(history_id, max_results, after_date, before_date)
