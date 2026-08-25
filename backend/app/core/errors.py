"""Typed application errors with a stable, non-sensitive public contract."""

from __future__ import annotations


class ApplicationError(Exception):
    """An expected failure whose public representation is safe by construction."""

    def __init__(
        self,
        *,
        code: str,
        message: str,
        status_code: int,
        category: str,
        hint: str | None = None,
        retriable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.category = category
        self.hint = hint
        self.retriable = retriable


class InvalidOperationError(ApplicationError):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        hint: str | None = None,
    ) -> None:
        super().__init__(
            code=code,
            message=message,
            status_code=400,
            category="invalid_operation",
            hint=hint,
        )


class InputValidationError(ApplicationError):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        hint: str | None = None,
    ) -> None:
        super().__init__(
            code=code,
            message=message,
            status_code=422,
            category="validation",
            hint=hint,
        )


class StateConflictError(ApplicationError):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        hint: str | None = None,
    ) -> None:
        super().__init__(
            code=code,
            message=message,
            status_code=409,
            category="state_conflict",
            hint=hint,
        )


class IntegrationUnavailableError(ApplicationError):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        hint: str | None = None,
        status_code: int = 502,
        retriable: bool = True,
    ) -> None:
        super().__init__(
            code=code,
            message=message,
            status_code=status_code,
            category="integration",
            hint=hint,
            retriable=retriable,
        )


class LocalOperationError(ApplicationError):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        hint: str | None = None,
        retriable: bool = True,
        status_code: int = 500,
    ) -> None:
        super().__init__(
            code=code,
            message=message,
            status_code=status_code,
            category="local_operation",
            hint=hint,
            retriable=retriable,
        )
