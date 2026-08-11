"""Per-request support correlation without accepting caller-controlled IDs."""

from __future__ import annotations

from contextvars import ContextVar
from uuid import uuid4


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
        state = scope.setdefault("state", {})
        state["request_id"] = request_id
        token = _request_id.set(request_id)

        async def send_with_request_id(message):
            if message.get("type") == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-godfin-request-id", request_id.encode("ascii")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            _request_id.reset(token)
