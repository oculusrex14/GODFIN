"""Explicit trust policy for GODFIN's local HTTP API.

The desktop renderer never receives the per-launch secret. Electron adds it at
the network boundary, while the frozen backend receives the same random value
through its child-process environment. Browser development remains usable on
loopback, and the separately enabled LAN mode has a deliberately broader,
typed policy with no implicit wildcard origins or DNS hostnames.
"""

from __future__ import annotations

import ipaddress
import os
import secrets
from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlsplit

from starlette.responses import JSONResponse

from app.core.api_errors import error_payload
from app.core.network_access import network_access_enabled
from app.core.request_context import new_request_id


class RuntimeMode(str, Enum):
    TEST = "test"
    LOCAL = "local"
    PACKAGED = "packaged"
    LAN = "lan"


LAUNCH_SECRET_HEADER = "x-godfin-launch"
_DEVELOPMENT_ORIGINS = (
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5200",
    "http://localhost:5173",
    "http://localhost:5200",
)
_PACKAGED_ORIGIN = "godfin://app"
_ALLOWED_BROWSER_PORTS = {5173, 5200}


def runtime_mode() -> RuntimeMode:
    """Resolve a typed mode and fail closed on an invalid explicit value."""

    explicit = os.environ.get("GODFIN_RUNTIME_MODE")
    if explicit:
        try:
            return RuntimeMode(explicit.strip().lower())
        except ValueError as exc:
            supported = ", ".join(mode.value for mode in RuntimeMode)
            raise RuntimeError(
                f"GODFIN_RUNTIME_MODE must be one of: {supported}"
            ) from exc
    if os.environ.get("GODFIN_TESTING") == "1":
        return RuntimeMode.TEST
    if network_access_enabled():
        return RuntimeMode.LAN
    if os.environ.get("GODFIN_PACKAGED") == "1":
        return RuntimeMode.PACKAGED
    return RuntimeMode.LOCAL


def _host_name(raw_host: str) -> str | None:
    try:
        parsed = urlsplit(f"//{raw_host}")
        if not parsed.hostname or parsed.username or parsed.password:
            return None
        return parsed.hostname.rstrip(".").lower()
    except ValueError:
        return None


def _private_or_loopback_ip(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return address.is_private or address.is_loopback or address.is_link_local


def _origin_parts(origin: str) -> tuple[str, str, int | None] | None:
    try:
        parsed = urlsplit(origin)
        if not parsed.scheme or not parsed.hostname:
            return None
        return parsed.scheme.lower(), parsed.hostname.rstrip(".").lower(), parsed.port
    except ValueError:
        return None


@dataclass(frozen=True)
class LocalApiPolicy:
    mode: RuntimeMode
    launch_secret: str | None

    @classmethod
    def from_environment(cls) -> "LocalApiPolicy":
        secret = os.environ.get("GODFIN_LAUNCH_SECRET")
        return cls(
            mode=runtime_mode(),
            launch_secret=secret if secret else None,
        )

    @property
    def cors_origins(self) -> tuple[str, ...]:
        if self.mode is RuntimeMode.PACKAGED:
            return (_PACKAGED_ORIGIN,)
        if self.mode is RuntimeMode.LAN:
            return (*_DEVELOPMENT_ORIGINS, _PACKAGED_ORIGIN)
        if self.mode is RuntimeMode.LOCAL and self.launch_secret:
            return (*_DEVELOPMENT_ORIGINS, _PACKAGED_ORIGIN)
        return _DEVELOPMENT_ORIGINS

    @property
    def cors_origin_regex(self) -> str | None:
        if self.mode is not RuntimeMode.LAN:
            return None
        # The trust middleware performs strict IP parsing before CORS runs.
        # This regex only enables the matching CORS response for private IPv4
        # browser origins used by the supported Vite LAN workflow.
        return (
            r"^http://(?:10(?:\.\d{1,3}){3}|"
            r"192\.168(?:\.\d{1,3}){2}|"
            r"172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})"
            r":(?:5173|5200)$"
        )

    def host_allowed(self, raw_host: str | None) -> bool:
        if not raw_host:
            return False
        hostname = _host_name(raw_host)
        if hostname is None:
            return False
        if self.mode is RuntimeMode.TEST:
            return hostname in {"testserver", "localhost", "127.0.0.1", "::1"}
        if self.mode is RuntimeMode.PACKAGED:
            return hostname == "127.0.0.1"
        if self.mode is RuntimeMode.LOCAL:
            return hostname in {"localhost", "127.0.0.1", "::1"}
        return hostname == "localhost" or _private_or_loopback_ip(hostname)

    def origin_allowed(self, origin: str | None) -> bool:
        if not origin:
            return True
        if origin in self.cors_origins:
            return True
        if self.mode is not RuntimeMode.LAN:
            return False
        parts = _origin_parts(origin)
        if parts is None:
            return False
        scheme, hostname, port = parts
        return (
            scheme == "http"
            and port in _ALLOWED_BROWSER_PORTS
            and _private_or_loopback_ip(hostname)
        )

    def launch_secret_allowed(self, supplied: str | None, method: str) -> bool:
        if method == "OPTIONS" or not self.launch_secret:
            return True
        # LAN mode is a separate, explicitly enabled bearer-authenticated API
        # policy. The Electron renderer still sends its secret, but supported
        # private-network clients are not expected to possess a process secret.
        if self.mode is RuntimeMode.LAN:
            return True
        return bool(supplied) and secrets.compare_digest(
            supplied,
            self.launch_secret,
        )


class LocalApiTrustMiddleware:
    """Reject requests outside the active local API trust boundary."""

    def __init__(self, app, *, policy: LocalApiPolicy):
        self.app = app
        self.policy = policy

    async def _reject(self, scope, receive, send, *, code: str, message: str) -> None:
        request_id = new_request_id()
        response = JSONResponse(
            status_code=403,
            headers={"X-GODFIN-Request-ID": request_id},
            content=error_payload(
                code=code,
                message=message,
                category="authorization",
                hint="Open GODFIN from its trusted desktop app or local address.",
                retriable=False,
                request_id=request_id,
            ),
        )
        await response(scope, receive, send)

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        header_values: dict[str, list[str]] = {}
        for key, value in scope.get("headers", []):
            name = key.decode("latin-1").lower()
            header_values.setdefault(name, []).append(value.decode("latin-1"))
        hosts = header_values.get("host", [])
        origins = header_values.get("origin", [])
        launch_secrets = header_values.get(LAUNCH_SECRET_HEADER, [])
        if len(hosts) != 1 or len(origins) > 1 or len(launch_secrets) > 1:
            await self._reject(
                scope,
                receive,
                send,
                code="AMBIGUOUS_LOCAL_TRUST_HEADERS",
                message="This request contains ambiguous local security headers.",
            )
            return
        if not self.policy.host_allowed(hosts[0]):
            await self._reject(
                scope,
                receive,
                send,
                code="UNTRUSTED_LOCAL_HOST",
                message="This request did not use a trusted GODFIN local address.",
            )
            return
        if not self.policy.origin_allowed(origins[0] if origins else None):
            await self._reject(
                scope,
                receive,
                send,
                code="UNTRUSTED_LOCAL_ORIGIN",
                message="This page is not allowed to connect to GODFIN.",
            )
            return
        if not self.policy.launch_secret_allowed(
            launch_secrets[0] if launch_secrets else None,
            scope.get("method", "GET"),
        ):
            await self._reject(
                scope,
                receive,
                send,
                code="MISSING_LAUNCH_TRUST",
                message="This request did not come through the active GODFIN app.",
            )
            return
        await self.app(scope, receive, send)
