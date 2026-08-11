from __future__ import annotations

import ast
import logging
import re
from pathlib import Path


ENDPOINT_ROOT = Path(__file__).parents[1] / "app" / "api" / "v1" / "endpoints"
REQUEST_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
PUBLIC_ERROR_CALLS = {
    "ApplicationError",
    "HTTPException",
    "InputValidationError",
    "IntegrationUnavailableError",
    "InvalidOperationError",
    "LocalOperationError",
    "StateConflictError",
}


def _assert_correlated_error(response, *, code: str) -> dict:
    payload = response.json()
    assert payload["code"] == code
    assert REQUEST_ID_PATTERN.fullmatch(payload["request_id"])
    assert response.headers["x-godfin-request-id"] == payload["request_id"]
    assert payload["detail"] == payload["message"]
    assert isinstance(payload["category"], str) and payload["category"]
    assert isinstance(payload["retriable"], bool)
    return payload


def _name_of_call(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def test_endpoint_exception_handlers_never_build_public_errors_from_exception_text():
    violations: list[str] = []
    for path in sorted(ENDPOINT_ROOT.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for handler in (node for node in ast.walk(tree) if isinstance(node, ast.ExceptHandler)):
            if not handler.name:
                continue
            for node in ast.walk(ast.Module(body=handler.body, type_ignores=[])):
                public_value = None
                if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
                    if _name_of_call(node.exc) in PUBLIC_ERROR_CALLS:
                        public_value = node.exc
                elif isinstance(node, ast.Return):
                    public_value = node.value
                if public_value is None:
                    continue
                if any(
                    isinstance(child, ast.Name) and child.id == handler.name
                    for child in ast.walk(public_value)
                ):
                    violations.append(f"{path.name}:{getattr(node, 'lineno', 0)}")
    assert violations == []


def test_validation_and_trust_errors_return_correlated_request_ids(client, auth_client):
    validation = auth_client.get(
        "/api/v1/transactions?page=0",
        headers={"X-GODFIN-Request-ID": "caller-controlled"},
    )
    _assert_correlated_error(validation, code="VALIDATION_ERROR")
    assert validation.json()["request_id"] != "caller-controlled"

    healthy = client.get("/api/v1/health")
    assert healthy.status_code == 200
    assert REQUEST_ID_PATTERN.fullmatch(healthy.headers["x-godfin-request-id"])

    rejected_host = client.get(
        "/api/v1/health",
        headers={"Host": "untrusted.example"},
    )
    payload = _assert_correlated_error(rejected_host, code="UNTRUSTED_LOCAL_HOST")
    assert payload["category"] == "authorization"


def test_backup_fault_is_safe_correlated_and_structured(
    auth_client,
    monkeypatch,
    caplog,
):
    leaked = "/Users/private/backups/godfin.db token=backup-secret"

    def fail_backup(*_args, **_kwargs):
        raise OSError(leaked)

    monkeypatch.setattr(
        "app.api.v1.endpoints.settings.create_backup",
        fail_backup,
    )
    with caplog.at_level(logging.ERROR, logger="app.core.api_errors"):
        response = auth_client.post("/api/v1/settings/backup")

    payload = _assert_correlated_error(response, code="BACKUP_FAILED")
    assert response.status_code == 500
    assert leaked not in response.text
    record = next(
        item for item in caplog.records if getattr(item, "error_code", None) == "BACKUP_FAILED"
    )
    assert record.request_id == payload["request_id"]
    assert record.operation_id == "trigger_backup"
    assert record.cause_type == "OSError"


def test_gmail_sync_fault_never_exposes_provider_or_path_details(
    auth_client,
    monkeypatch,
):
    leaked = "oauth token=mail-secret at /Users/private/token.json"
    monkeypatch.setattr("app.api.v1.endpoints.gmail.is_connected", lambda: True)

    def fail_sync(_db):
        raise RuntimeError(leaked)

    monkeypatch.setattr("app.api.v1.endpoints.gmail.run_initial_sync", fail_sync)
    response = auth_client.post("/api/v1/ingest/gmail/initial")

    payload = _assert_correlated_error(response, code="GMAIL_SYNC_FAILED")
    assert response.status_code == 502
    assert payload["category"] == "integration"
    assert leaked not in response.text


def test_llm_connection_fault_is_not_returned_as_http_success(
    auth_client,
    monkeypatch,
):
    leaked = "provider key sk-private at /Users/private/llm.json"
    monkeypatch.setattr(
        "app.api.v1.endpoints.llm.enforce_feature",
        lambda *_args, **_kwargs: None,
    )

    def fail_provider(**_kwargs):
        raise RuntimeError(leaked)

    monkeypatch.setattr("app.api.v1.endpoints.llm.create_provider", fail_provider)
    response = auth_client.post(
        "/api/v1/llm/config/test",
        json={"provider": "ollama", "model": "qwen"},
    )

    payload = _assert_correlated_error(response, code="LLM_CONNECTION_FAILED")
    assert response.status_code == 502
    assert payload["retriable"] is True
    assert leaked not in response.text


def test_llm_provider_failure_message_is_never_reflected(
    auth_client,
    monkeypatch,
):
    leaked = "authentication failed for sk-private in /Users/private/config"
    monkeypatch.setattr(
        "app.api.v1.endpoints.llm.enforce_feature",
        lambda *_args, **_kwargs: None,
    )

    class FailedProvider:
        def test_connection(self):
            return False, leaked

    monkeypatch.setattr(
        "app.api.v1.endpoints.llm.create_provider",
        lambda **_kwargs: FailedProvider(),
    )
    response = auth_client.post(
        "/api/v1/llm/config/test",
        json={"provider": "ollama", "model": "qwen"},
    )

    payload = _assert_correlated_error(response, code="LLM_CONNECTION_FAILED")
    assert response.status_code == 502
    assert payload["message"] == "GODFIN could not connect to that AI provider."
    assert leaked not in response.text


def test_audit_database_fault_rolls_back_and_returns_stable_error(
    auth_client,
    monkeypatch,
):
    leaked = "sqlite:///Users/private/godfin.db row=secret"

    def fail_finalize(*_args, **_kwargs):
        raise RuntimeError(leaked)

    monkeypatch.setattr(
        "app.api.v1.endpoints.audit.finalize_audit",
        fail_finalize,
    )
    response = auth_client.post("/api/v1/audit/example-session/finalize")

    payload = _assert_correlated_error(response, code="AUDIT_FINALIZE_FAILED")
    assert response.status_code == 500
    assert payload["category"] == "local_operation"
    assert leaked not in response.text
