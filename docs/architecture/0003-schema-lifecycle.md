# ADR-0003: Ordered startup migrations without Alembic

Status: Accepted
Date: 11 August 2026

## Context

The historical Alembic chain was incomplete and was never the packaged
application's production upgrade path.

## Decision

Fresh profiles use SQLAlchemy `create_all`. Existing profiles use the ordered,
idempotent registry in `backend/app/core/startup_migrations.py` after a verified
backup. Each revision has preconditions/postconditions and records completion
only after validation. Alembic is unsupported and its stale revisions remain
removed.

## Consequences

Every schema change needs clean-bootstrap, prior-revision, repeat-run,
interruption, future-revision, and restore tests. Binary rollback restores a
verified pre-upgrade database snapshot rather than downgrading schema in place.
