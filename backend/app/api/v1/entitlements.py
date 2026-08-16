"""HTTP entitlement adapters and auditable FastAPI dependencies.

Domain entitlement decisions remain in :mod:`app.core.license`.  This module
only translates those decisions into the stable public HTTP contract and tags
route dependencies so CI can audit every paid API surface.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache
from typing import Any, TypeVar

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import ApplicationError
from app.core.feature_flags import FeatureDisabledError, require_feature_flag
from app.core.license import LicenseError, require_feature

ENTITLEMENT_MARKER = "__godfin_entitlement_feature__"
CONDITIONAL_ENTITLEMENT_MARKER = "__godfin_conditional_entitlement_feature__"

Endpoint = TypeVar("Endpoint", bound=Callable[..., Any])


def raise_license_error(exc: LicenseError) -> None:
    raise HTTPException(
        status_code=exc.status_code,
        detail={
            "code": exc.code,
            "message": exc.public_message,
            "hint": "Open godfin.dev/account if you need the key resent.",
            "retriable": exc.retriable,
        },
    ) from exc


def enforce_feature(db: Session, feature: str) -> None:
    """Enforce one paid feature and preserve the public license error shape."""

    try:
        require_feature(db, feature)
    except LicenseError as exc:
        raise_license_error(exc)


@lru_cache(maxsize=None)
def require_entitlement(
    feature: str,
    feature_flag: str | None = None,
    unavailable_message: str | None = None,
) -> Callable[..., None]:
    """Return a declarative FastAPI dependency for a paid feature.

    The marker is intentionally attached to the dependency callable.  The
    route-policy contract test reads it from FastAPI's dependency graph and
    fails if a mapped route loses its gate.
    """

    def dependency(db: Session = Depends(get_db)) -> None:
        if feature_flag:
            try:
                require_feature_flag(db, feature_flag)
            except FeatureDisabledError as exc:
                raise ApplicationError(
                    code="FEATURE_UNAVAILABLE",
                    message=(
                        unavailable_message
                        or "This feature is not available in this build."
                    ),
                    status_code=404,
                    category="availability",
                ) from exc
        enforce_feature(db, feature)

    dependency.__name__ = f"require_{feature}_entitlement"
    setattr(dependency, ENTITLEMENT_MARKER, feature)
    return dependency


def conditional_entitlement(feature: str) -> Callable[[Endpoint], Endpoint]:
    """Declare a route whose paid gate depends on the submitted resource.

    Conditional routes still call :func:`enforce_feature` in the validated
    branch.  The marker makes that policy machine-readable without charging
    free-tier users for the supported free branch.
    """

    def decorate(endpoint: Endpoint) -> Endpoint:
        setattr(endpoint, CONDITIONAL_ENTITLEMENT_MARKER, feature)
        return endpoint

    return decorate
