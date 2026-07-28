from __future__ import annotations

import logging
from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

logger = logging.getLogger(__name__)


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
    hint: str | None = None,
    retriable: bool = False,
) -> dict[str, Any]:
    # ``detail`` remains during the compatibility window for existing local
    # clients; all new clients consume the standard top-level fields.
    return {
        "code": code,
        "message": message,
        "hint": hint,
        "retriable": retriable,
        "detail": message,
    }


async def http_exception_handler(
    _request: Request,
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
    return JSONResponse(
        status_code=exc.status_code,
        headers=exc.headers,
        content=error_payload(
            code=code,
            message=message,
            hint=hint,
            retriable=retriable,
        ),
    )


async def validation_exception_handler(
    _request: Request,
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
            hint="Check the highlighted value and try again.",
            retriable=False,
        ),
    )


async def unhandled_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    logger.exception("Unhandled API error on %s", request.url.path, exc_info=exc)
    return JSONResponse(
        status_code=500,
        content=error_payload(
            code="INTERNAL_ERROR",
            message="GODFIN could not complete that request.",
            hint="Try again. If it continues, open Settings and check service health.",
            retriable=True,
        ),
    )
