"""Application-wide request-body limits for the local API."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from starlette.responses import JSONResponse

from app.core.api_errors import error_payload


MAX_REQUEST_BODY_BYTES = 32 * 1024 * 1024
_BODY_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class _RequestBodyTooLarge(Exception):
    pass


class RequestBodyLimitMiddleware:
    """Reject oversized fixed-length and streamed request bodies.

    Statement uploads retain their stricter endpoint-specific 10 MB limit.
    This outer ceiling protects every current and future mutation endpoint,
    including callers that omit ``Content-Length`` and stream chunks.
    """

    def __init__(self, app, *, max_bytes: int = MAX_REQUEST_BODY_BYTES):
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        self.app = app
        self.max_bytes = max_bytes

    async def _error_response(
        self,
        scope,
        receive,
        send,
        *,
        status_code: int,
        code: str,
        message: str,
        hint: str,
    ) -> None:
        response = JSONResponse(
            status_code=status_code,
            headers={"connection": "close"},
            content=error_payload(
                code=code,
                message=message,
                hint=hint,
                retriable=False,
            ),
        )
        await response(scope, receive, send)

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[dict[str, Any]]],
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        if scope.get("type") != "http" or scope.get("method") not in _BODY_METHODS:
            await self.app(scope, receive, send)
            return

        headers = [
            (key.lower(), value)
            for key, value in scope.get("headers", [])
        ]
        content_lengths = [value for key, value in headers if key == b"content-length"]
        transfer_encodings = [
            value for key, value in headers if key == b"transfer-encoding"
        ]
        if len(content_lengths) > 1 or (content_lengths and transfer_encodings):
            await self._error_response(
                scope,
                receive,
                send,
                status_code=400,
                code="AMBIGUOUS_BODY_LENGTH",
                message="Request body length headers are ambiguous.",
                hint="Send one Content-Length value or use chunked transfer encoding.",
            )
            return
        raw_length = content_lengths[0] if content_lengths else None
        if raw_length is not None:
            try:
                content_length = int(raw_length)
            except (TypeError, ValueError):
                await self._error_response(
                    scope,
                    receive,
                    send,
                    status_code=400,
                    code="INVALID_CONTENT_LENGTH",
                    message="Content-Length must be a non-negative integer.",
                    hint="Send the request again with a valid body length.",
                )
                return
            if content_length < 0:
                await self._error_response(
                    scope,
                    receive,
                    send,
                    status_code=400,
                    code="INVALID_CONTENT_LENGTH",
                    message="Content-Length must be a non-negative integer.",
                    hint="Send the request again with a valid body length.",
                )
                return
            if content_length > self.max_bytes:
                await self._error_response(
                    scope,
                    receive,
                    send,
                    status_code=413,
                    code="REQUEST_TOO_LARGE",
                    message="Request body is too large.",
                    hint=f"Keep the complete request below {self.max_bytes} bytes.",
                )
                return

        received = 0

        async def limited_receive() -> dict[str, Any]:
            nonlocal received
            message = await receive()
            if message.get("type") == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise _RequestBodyTooLarge
            return message

        response_started = False

        async def tracked_send(message: dict[str, Any]) -> None:
            nonlocal response_started
            if message.get("type") == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracked_send)
        except _RequestBodyTooLarge:
            if response_started:
                raise
            await self._error_response(
                scope,
                receive,
                send,
                status_code=413,
                code="REQUEST_TOO_LARGE",
                message="Request body is too large.",
                hint=f"Keep the complete request below {self.max_bytes} bytes.",
            )
