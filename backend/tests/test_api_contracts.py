from __future__ import annotations

import ast
import asyncio
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from app.core.request_limits import (
    MAX_REQUEST_BODY_BYTES,
    RequestBodyLimitMiddleware,
)
from app.models.app_setting import AppSetting
from app.models.goal import Goal
from tests.license_helpers import install_test_license


ENDPOINT_ROOT = Path(__file__).parents[1] / "app" / "api" / "v1" / "endpoints"
STANDARD_ERROR_CODES = {
    "400",
    "401",
    "403",
    "404",
    "409",
    "410",
    "413",
    "422",
    "429",
    "500",
    "502",
    "503",
}
PUBLIC_ROUTES = {
    ("auth.py", "auth_status"),
    ("auth.py", "set_pin"),
    ("auth.py", "verify_pin"),
    ("gmail.py", "gmail_oauth_callback"),
    ("health.py", "health_check"),
    ("health.py", "readiness_check"),
}
TERMINAL_OPERATIONS = {
    "upload_statement_legacy_api_v1_ingest_upload_post",
}


def _activate_max(db) -> None:
    install_test_license(db, "max")


def _assert_error_shape(response, *, code: str) -> None:
    payload = response.json()
    assert payload["code"] == code
    assert isinstance(payload["message"], str) and payload["message"]
    assert isinstance(payload["category"], str) and payload["category"]
    assert "hint" in payload
    assert payload["retriable"] is False
    assert payload["detail"] == payload["message"]
    assert len(payload["request_id"]) == 32
    assert response.headers["x-godfin-request-id"] == payload["request_id"]


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        (
            "POST",
            "/api/v1/advisor/chat",
            {
                "message": "Explain this",
                "history": [
                    {"role": "user", "content": "hello"}
                    for _ in range(21)
                ],
            },
        ),
        (
            "PUT",
            "/api/v1/accounts/sender-mappings",
            {
                "mappings": [
                    {
                        "sender_pattern": f"sender-{index}@example.com",
                        "parser_profile": "hdfc_savings",
                        "account_id": "example-account",
                    }
                    for index in range(101)
                ],
            },
        ),
        (
            "POST",
            "/api/v1/llm/config/test",
            {"provider": "ollama", "model": "m" * 201},
        ),
        (
            "POST",
            "/api/v1/settings/developer/rules",
            {
                "rule_type": "contains",
                "pattern": "x" * 1001,
                "category": "FOOD & DINING",
            },
        ),
        (
            "PUT",
            "/api/v1/system/local-ai/choice",
            {"choice": "silently-install-anything"},
        ),
    ],
)
def test_bounded_request_contracts_reject_oversized_or_unknown_values(
    auth_client,
    db_session,
    method,
    path,
    payload,
):
    # Paid dependencies intentionally run before request-body validation, so
    # activate the test entitlement before exercising the validation contract.
    _activate_max(db_session)
    response = auth_client.request(method, path, json=payload)
    assert response.status_code == 422
    _assert_error_shape(response, code="VALIDATION_ERROR")


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/dashboard/stats?month=2026-00",
        "/api/v1/dashboard/stats?month=2026-99",
        "/api/v1/income/stats?month=2026-13",
        "/api/v1/transactions?page=0",
        "/api/v1/transactions?page_size=201",
        "/api/v1/auth/gmail/callback?code=ok&state=short",
    ],
)
def test_semantic_dates_pagination_and_oauth_bounds_are_structured_422s(
    auth_client,
    path,
):
    response = auth_client.get(path)
    assert response.status_code == 422
    _assert_error_shape(response, code="VALIDATION_ERROR")


def test_fixed_length_request_over_global_limit_is_rejected_before_parsing(client):
    response = client.post(
        "/api/v1/auth/verify-pin",
        content=b"{}",
        headers={
            "content-type": "application/json",
            "content-length": str(MAX_REQUEST_BODY_BYTES + 1),
        },
    )

    assert response.status_code == 413
    _assert_error_shape(response, code="REQUEST_TOO_LARGE")


def _run_limit_middleware(*, headers, chunks, max_bytes=5):
    messages = [
        {
            "type": "http.request",
            "body": chunk,
            "more_body": index < len(chunks) - 1,
        }
        for index, chunk in enumerate(chunks)
    ]
    sent = []

    async def receive():
        return messages.pop(0)

    async def send(message):
        sent.append(message)

    async def consuming_app(_scope, receive_message, send_message):
        while True:
            message = await receive_message()
            if not message.get("more_body"):
                break
        await send_message(
            {"type": "http.response.start", "status": 200, "headers": []}
        )
        await send_message({"type": "http.response.body", "body": b"ok"})

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/test",
        "headers": headers,
    }
    middleware = RequestBodyLimitMiddleware(consuming_app, max_bytes=max_bytes)
    asyncio.run(middleware(scope, receive, send))
    return sent


def test_chunked_request_over_global_limit_is_rejected_without_content_length():
    sent = _run_limit_middleware(headers=[], chunks=[b"abc", b"def"])

    assert sent[0]["status"] == 413
    body = b"".join(
        message.get("body", b"")
        for message in sent
        if message["type"] == "http.response.body"
    )
    assert json.loads(body)["code"] == "REQUEST_TOO_LARGE"


def test_invalid_content_length_uses_standard_error_contract():
    sent = _run_limit_middleware(
        headers=[(b"content-length", b"not-a-number")],
        chunks=[b"{}"],
    )

    assert sent[0]["status"] == 400
    body = b"".join(
        message.get("body", b"")
        for message in sent
        if message["type"] == "http.response.body"
    )
    payload = json.loads(body)
    assert payload["code"] == "INVALID_CONTENT_LENGTH"
    assert payload["detail"] == payload["message"]


@pytest.mark.parametrize(
    "headers",
    [
        [(b"content-length", b"2"), (b"content-length", b"3")],
        [(b"content-length", b"2"), (b"transfer-encoding", b"chunked")],
    ],
)
def test_ambiguous_request_length_headers_are_rejected(headers):
    sent = _run_limit_middleware(headers=headers, chunks=[b"{}"])

    assert sent[0]["status"] == 400
    body = b"".join(
        message.get("body", b"")
        for message in sent
        if message["type"] == "http.response.body"
    )
    assert json.loads(body)["code"] == "AMBIGUOUS_BODY_LENGTH"


def test_digest_settings_get_does_not_create_default_rows(auth_client, db_session):
    keys = {
        "advisor_weekly_digest_enabled",
        "advisor_weekly_digest_recipient",
        "advisor_weekly_digest_last_sent",
    }
    db_session.query(AppSetting).filter(AppSetting.key.in_(keys)).delete(
        synchronize_session=False
    )
    db_session.commit()

    first = auth_client.get("/api/v1/advisor/digest/settings")
    second = auth_client.get("/api/v1/advisor/digest/settings")

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["enabled"] is False
    db_session.expire_all()
    assert db_session.query(AppSetting).filter(AppSetting.key.in_(keys)).count() == 0


def test_onboarding_get_does_not_materialize_or_repair_settings(
    auth_client,
    db_session,
):
    keys = {
        "onboarding_completed",
        "onboarding_deferred",
        "onboarding_step",
        "tutorial_step",
        "tutorial_completed_version",
    }
    db_session.query(AppSetting).filter(AppSetting.key.in_(keys)).delete(
        synchronize_session=False
    )
    db_session.commit()

    response = auth_client.get("/api/v1/onboarding")

    assert response.status_code == 200
    assert response.json()["step"] == 1
    assert response.json()["tutorial_step"] == 1
    db_session.expire_all()
    assert db_session.query(AppSetting).filter(AppSetting.key.in_(keys)).count() == 0


def test_goal_list_calculates_balance_without_rewriting_compatibility_column(
    auth_client,
    db_session,
):
    created = auth_client.post(
        "/api/v1/goals",
        json={
            "name": "Read-only balance",
            "target_amount": 1000,
            "current_saved": 125,
            "deadline_date": (date.today() + timedelta(days=365)).isoformat(),
        },
    )
    assert created.status_code == 201
    goal_id = created.json()["id"]
    db_session.expire_all()
    goal = db_session.query(Goal).filter_by(id=goal_id).one()
    goal.current_saved = 9999
    db_session.commit()

    response = auth_client.get("/api/v1/goals")

    assert response.status_code == 200
    returned = next(item for item in response.json() if item["id"] == goal_id)
    assert returned["current_saved"] == 125
    db_session.expire_all()
    assert db_session.query(Goal).filter_by(id=goal_id).one().current_saved == 9999


def test_get_route_functions_have_no_direct_database_mutators():
    forbidden_methods = {"add", "add_all", "commit", "delete", "flush", "merge", "update"}
    forbidden_helpers = {
        "_get_or_create_setting",
        "_get_setting",
        "recompute_goal_balance",
    }
    violations = []
    for path in sorted(ENDPOINT_ROOT.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            is_get = any(
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and decorator.func.attr == "get"
                for decorator in node.decorator_list
            )
            if not is_get:
                continue
            for call in (item for item in ast.walk(node) if isinstance(item, ast.Call)):
                name = None
                if isinstance(call.func, ast.Attribute):
                    name = call.func.attr
                elif isinstance(call.func, ast.Name):
                    name = call.func.id
                if name in forbidden_methods | forbidden_helpers:
                    violations.append(f"{path.name}:{call.lineno}:{node.name}:{name}")
    assert violations == []


def test_route_authentication_lint_has_only_reviewed_public_endpoints():
    unauthenticated = set()
    for path in sorted(ENDPOINT_ROOT.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            is_route = any(
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and decorator.func.attr in {"get", "post", "put", "patch", "delete"}
                for decorator in node.decorator_list
            )
            if not is_route:
                continue
            if "get_current_user" not in ast.unparse(node.args):
                unauthenticated.add((path.name, node.name))
    assert unauthenticated == PUBLIC_ROUTES


def test_openapi_documents_one_error_envelope_and_success_status_per_operation():
    from app.main import app

    app.openapi_schema = None
    schema = app.openapi()
    assert schema["components"]["schemas"]["APIErrorResponse"]["required"] == [
        "code",
        "message",
        "category",
        "hint",
        "retriable",
        "detail",
        "request_id",
    ]
    operation_ids = set()
    untyped_success = []
    for methods in schema["paths"].values():
        for method, operation in methods.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            assert operation["operationId"] not in operation_ids
            operation_ids.add(operation["operationId"])
            responses = operation["responses"]
            success_codes = [status for status in responses if status.startswith("2")]
            if operation["operationId"] in TERMINAL_OPERATIONS:
                assert success_codes == []
            else:
                assert len(success_codes) == 1
                success = responses[success_codes[0]]
                if success_codes[0] != "204":
                    content = success.get("content", {})
                    assert content, operation["operationId"]
                    success_schemas = [
                        media["schema"] for media in content.values()
                    ]
                    if any(
                        success_schema == {}
                        for success_schema in success_schemas
                    ):
                        untyped_success.append(operation["operationId"])
            assert STANDARD_ERROR_CODES <= responses.keys()
            for status in STANDARD_ERROR_CODES:
                error_schema = responses[status]["content"]["application/json"]["schema"]
                assert error_schema == {
                    "$ref": "#/components/schemas/APIErrorResponse"
                }
    assert len(operation_ids) == 182
    # Freeze the audited legacy debt: a new route may not add another generic
    # success body. Precise success schemas are being reduced separately while
    # every error/status/auth contract is enforced now.
    assert len(untyped_success) == 17
