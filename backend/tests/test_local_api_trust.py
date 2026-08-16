from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.testclient import TestClient

from app.core.local_api_trust import (
    LAUNCH_SECRET_HEADER,
    LocalApiPolicy,
    LocalApiTrustMiddleware,
    RuntimeMode,
    runtime_mode,
)
from app.core.network_access import NetworkAccessMode, network_access_mode


def _client(policy: LocalApiPolicy) -> TestClient:
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(policy.cors_origins),
        allow_origin_regex=policy.cors_origin_regex,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=["Content-Disposition", "Retry-After"],
    )
    app.add_middleware(LocalApiTrustMiddleware, policy=policy)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/v1/auth/gmail/callback")
    def gmail_callback():
        return {"status": "callback-reached"}

    @app.post("/api/v1/auth/gmail/callback")
    def gmail_callback_post():
        return {"status": "unexpected-post"}

    return TestClient(app, base_url="http://127.0.0.1:5100")


def test_packaged_policy_requires_exact_host_origin_and_launch_secret():
    policy = LocalApiPolicy(RuntimeMode.PACKAGED, "launch-secret")
    client = _client(policy)
    trusted = {
        "Origin": "godfin://app",
        LAUNCH_SECRET_HEADER: "launch-secret",
    }

    assert client.get("/health", headers=trusted).status_code == 200

    missing = client.get("/health", headers={"Origin": "godfin://app"})
    wrong = client.get(
        "/health",
        headers={"Origin": "godfin://app", LAUNCH_SECRET_HEADER: "wrong"},
    )
    unexpected_host = client.get(
        "/health",
        headers={**trusted, "Host": "localhost:5100"},
    )
    development_origin = client.get(
        "/health",
        headers={**trusted, "Origin": "http://localhost:5200"},
    )

    assert missing.status_code == 403
    assert missing.json()["code"] == "MISSING_LAUNCH_TRUST"
    assert wrong.status_code == 403
    assert unexpected_host.json()["code"] == "UNTRUSTED_LOCAL_HOST"
    assert development_origin.json()["code"] == "UNTRUSTED_LOCAL_ORIGIN"


def test_packaged_cors_is_exact_bounded_and_has_no_credentials_mode():
    client = _client(LocalApiPolicy(RuntimeMode.PACKAGED, "launch-secret"))
    response = client.options(
        "/health",
        headers={
            "Origin": "godfin://app",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization, Content-Type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "godfin://app"
    assert "access-control-allow-credentials" not in response.headers
    allowed_methods = response.headers["access-control-allow-methods"]
    assert "*" not in allowed_methods
    assert "GET" in allowed_methods
    assert "POST" in allowed_methods


def test_packaged_policy_allows_only_exact_browser_oauth_callback_without_secret():
    client = _client(LocalApiPolicy(RuntimeMode.PACKAGED, "launch-secret"))

    callback = client.get(
        "/api/v1/auth/gmail/callback?code=provider-code&state=one-time-state",
    )
    callback_post = client.post("/api/v1/auth/gmail/callback")
    callback_suffix = client.get("/api/v1/auth/gmail/callback/extra")
    untrusted_host = client.get(
        "/api/v1/auth/gmail/callback",
        headers={"Host": "localhost:5100"},
    )
    untrusted_origin = client.get(
        "/api/v1/auth/gmail/callback",
        headers={"Origin": "https://attacker.invalid"},
    )

    assert callback.status_code == 200
    assert callback.json() == {"status": "callback-reached"}
    assert callback_post.status_code == 403
    assert callback_post.json()["code"] == "MISSING_LAUNCH_TRUST"
    assert callback_suffix.status_code == 403
    assert callback_suffix.json()["code"] == "MISSING_LAUNCH_TRUST"
    assert untrusted_host.status_code == 403
    assert untrusted_host.json()["code"] == "UNTRUSTED_LOCAL_HOST"
    assert untrusted_origin.status_code == 403
    assert untrusted_origin.json()["code"] == "UNTRUSTED_LOCAL_ORIGIN"


def test_local_mode_rejects_dns_rebinding_and_unlisted_origins():
    client = _client(LocalApiPolicy(RuntimeMode.LOCAL, None))

    assert client.get(
        "/health",
        headers={"Host": "localhost:5100", "Origin": "http://localhost:5200"},
    ).status_code == 200
    assert client.get(
        "/health",
        headers={"Host": "godfin.attacker.invalid:5100"},
    ).json()["code"] == "UNTRUSTED_LOCAL_HOST"
    assert client.get(
        "/health",
        headers={"Origin": "https://attacker.invalid"},
    ).json()["code"] == "UNTRUSTED_LOCAL_ORIGIN"


def test_duplicate_security_headers_are_rejected_before_routing():
    client = _client(LocalApiPolicy(RuntimeMode.LOCAL, None))
    response = client.get(
        "/health",
        headers=[
            ("Host", "127.0.0.1:5100"),
            ("Host", "localhost:5100"),
        ],
    )
    assert response.status_code == 403
    assert response.json()["code"] == "AMBIGUOUS_LOCAL_TRUST_HEADERS"


@pytest.mark.parametrize(
    ("host", "origin", "allowed"),
    [
        ("192.168.1.10:5100", "http://192.168.1.10:5200", True),
        ("10.0.0.8:5100", "http://10.0.0.8:5173", True),
        ("172.16.0.5:5100", "http://172.16.0.5:5200", True),
        ("8.8.8.8:5100", "http://8.8.8.8:5200", False),
        ("money.local:5100", "http://192.168.1.10:5200", False),
        ("192.168.1.10:5100", "https://192.168.1.10:5200", False),
        ("192.168.1.10:5100", "http://192.168.1.10:8080", False),
    ],
)
def test_lan_mode_accepts_only_private_literal_addresses(
    host: str,
    origin: str,
    allowed: bool,
):
    client = _client(LocalApiPolicy(RuntimeMode.LAN, "desktop-secret"))
    response = client.get("/health", headers={"Host": host, "Origin": origin})
    assert (response.status_code == 200) is allowed


def test_explicit_runtime_mode_is_typed_and_invalid_values_fail_closed(monkeypatch):
    monkeypatch.setenv("GODFIN_RUNTIME_MODE", "packaged")
    assert runtime_mode() is RuntimeMode.PACKAGED

    monkeypatch.setenv("GODFIN_RUNTIME_MODE", "anything-goes")
    with pytest.raises(RuntimeError, match="GODFIN_RUNTIME_MODE"):
        runtime_mode()


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("local", NetworkAccessMode.LOCAL),
        ("false", NetworkAccessMode.LOCAL),
        ("lan", NetworkAccessMode.LAN),
        ("true", NetworkAccessMode.LAN),
        ("untyped-value", NetworkAccessMode.LOCAL),
    ],
)
def test_network_access_override_resolves_to_typed_mode(
    monkeypatch,
    value: str,
    expected: NetworkAccessMode,
):
    monkeypatch.setenv("GODFIN_ALLOW_NETWORK_ACCESS", value)
    assert network_access_mode() is expected


def test_desktop_wires_secret_and_mode_aware_bind_without_renderer_exposure():
    repository_root = Path(__file__).resolve().parents[2]
    desktop_source = (repository_root / "desktop" / "main.cjs").read_text()
    entry_source = (repository_root / "backend" / "desktop_entry.py").read_text()

    assert 'randomBytes(32).toString("base64url")' in desktop_source
    assert "GODFIN_PACKAGE_VERIFICATION_SECRET" in desktop_source
    assert "GODFIN_LAUNCH_SECRET: launchSecret" in desktop_source
    assert "configureBackendRequestTrust();" in desktop_source
    assert "[LAUNCH_SECRET_HEADER]: launchSecret" in desktop_source
    assert "host=bind_host()" in entry_source
    assert "proxy_headers=False" in entry_source
