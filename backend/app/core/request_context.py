"""Per-request support correlation without accepting caller-controlled IDs."""

from __future__ import annotations

from contextvars import ContextVar
from time import perf_counter
from uuid import uuid4

from app.core.local_metrics import record_request


_request_id: ContextVar[str | None] = ContextVar("godfin_request_id", default=None)


def new_request_id() -> str:
    return uuid4().hex


def current_request_id() -> str | None:
    return _request_id.get()


class RequestContextMiddleware:
    """Assign a random ID and attach it to every normal HTTP response."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        request_id = new_request_id()
        started = perf_counter()
        status_code = 500
        state = scope.setdefault("state", {})
        state["request_id"] = request_id
        token = _request_id.set(request_id)

        async def send_with_request_id(message):
            nonlocal status_code
            if message.get("type") == "http.response.start":
                status_code = int(message.get("status") or 500)
                headers = list(message.get("headers", []))
                headers.append((b"x-godfin-request-id", request_id.encode("ascii")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            route = scope.get("route")
            operation = str(
                getattr(route, "name", None)
                or getattr(route, "path", None)
                or "unmatched"
            )
            record_request(
                str(scope.get("method") or "UNKNOWN"),
                operation,
                status_code,
                (perf_counter() - started) * 1000,
            )
            _request_id.reset(token)
