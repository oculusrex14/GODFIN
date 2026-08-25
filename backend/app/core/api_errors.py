from __future__ import annotations

import logging
from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException

from app.core.errors import ApplicationError
from app.core.request_context import current_request_id, new_request_id

logger = logging.getLogger(__name__)


class APIErrorResponse(BaseModel):
    """The one public error contract returned by every API failure path."""

    code: str
    message: str
    category: str
    hint: str | None
    retriable: bool
    detail: str
    request_id: str


STANDARD_ERROR_RESPONSES = {
    status: {
        "model": APIErrorResponse,
        "description": description,
    }
    for status, description in {
        400: "Invalid request",
        401: "Authentication required",
        403: "Action not permitted",
        404: "Resource not found",
        409: "Request conflicts with current state",
        410: "Endpoint or resource is no longer available",
        413: "Request body is too large",
        422: "Request validation failed",
        429: "Request rate limit reached",
        500: "Unexpected local service error",
        502: "Upstream service returned an invalid response",
        503: "Service temporarily unavailable",
    }.items()
}


def _message(detail: Any, fallback: str) -> str:
    if isinstance(detail, str):
        return detail
    if isinstance(detail, dict):
        return str(detail.get("message") or detail.get("detail") or fallback)
    return fallback


def error_payload(
    *,
    code: str,
    message: str,
    category: str = "request",
    hint: str | None = None,
    retriable: bool = False,
    request_id: str | None = None,
) -> dict[str, Any]:
    # ``detail`` remains during the compatibility window for existing local
    # clients; all new clients consume the standard top-level fields.
    return {
        "code": code,
        "message": message,
        "category": category,
        "hint": hint,
        "retriable": retriable,
        "detail": message,
        "request_id": request_id or current_request_id() or new_request_id(),
    }


def _operation_name(request: Request) -> str:
    route = request.scope.get("route")
    return str(getattr(route, "name", None) or request.url.path)


def _log_server_error(
    request: Request,
    *,
    code: str,
    cause: BaseException | None,
) -> None:
    logger.error(
        "API operation failed",
        extra={
            "request_id": getattr(request.state, "request_id", None),
            "operation_id": _operation_name(request),
            "error_code": code,
            "cause_type": type(cause).__name__ if cause else None,
        },
        exc_info=(type(cause), cause, cause.__traceback__) if cause else None,
    )


def _category_for_status(status_code: int) -> str:
    if status_code in {401, 403}:
        return "authorization"
    if status_code == 409:
        return "state_conflict"
    if status_code in {502, 503}:
        return "integration"
    if status_code >= 500:
        return "local_operation"
    return "request"


async def application_exception_handler(
    request: Request,
    exc: ApplicationError,
) -> JSONResponse:
    if exc.status_code >= 500:
        _log_server_error(request, code=exc.code, cause=exc.__cause__ or exc)
    return JSONResponse(
        status_code=exc.status_code,
        content=error_payload(
            code=exc.code,
            message=exc.message,
            category=exc.category,
            hint=exc.hint,
            retriable=exc.retriable,
            request_id=getattr(request.state, "request_id", None),
        ),
    )


async def http_exception_handler(
    request: Request,
    exc: HTTPException,
) -> JSONResponse:
    message = _message(exc.detail, "Request failed")
    code = (
        exc.detail.get("code")
        if isinstance(exc.detail, dict) and exc.detail.get("code")
        else f"HTTP_{exc.status_code}"
    )
    hint = exc.detail.get("hint") if isinstance(exc.detail, dict) else None
    retriable = (
        bool(exc.detail.get("retriable"))
        if isinstance(exc.detail, dict)
        else exc.status_code >= 500 or exc.status_code == 429
    )
    if exc.status_code >= 500:
        _log_server_error(
            request,
            code=str(code),
            cause=exc.__cause__,
        )
    return JSONResponse(
        status_code=exc.status_code,
        headers=exc.headers,
        content=error_payload(
            code=code,
            message=message,
            category=_category_for_status(exc.status_code),
            hint=hint,
            retriable=retriable,
        ),
    )


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    first = exc.errors()[0] if exc.errors() else {}
    location = ".".join(str(part) for part in first.get("loc", ()) if part != "body")
    validation_message = first.get("msg", "Invalid request")
    message = f"{location}: {validation_message}" if location else validation_message
    return JSONResponse(
        status_code=422,
        content=error_payload(
            code="VALIDATION_ERROR",
            message=message,
            category="validation",
            hint="Check the highlighted value and try again.",
            retriable=False,
            request_id=getattr(request.state, "request_id", None),
        ),
    )


async def unhandled_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    _log_server_error(request, code="INTERNAL_ERROR", cause=exc)
    return JSONResponse(
        status_code=500,
        content=error_payload(
            code="INTERNAL_ERROR",
            message="GODFIN could not complete that request.",
            category="local_operation",
            hint="Try again. If it continues, open Settings and check service health.",
            retriable=True,
        ),
    )
