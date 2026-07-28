# GODFIN local database lifecycle

GODFIN deliberately uses one local SQLite database per desktop profile. It
does not use a hosted application database and it does not maintain an Alembic
revision chain.

## Startup strategy

1. Resolve the database path inside the Electron user-data directory (or the
   configured development path).
2. Open SQLite in WAL mode with foreign keys enabled.
3. Run SQLAlchemy `Base.metadata.create_all()` so all missing tables and indexes
   are created idempotently.
4. Run `_migrate_schema()` for narrowly scoped, idempotent upgrades needed by
   older local databases.
5. Run seeds with existence checks. HDFC profiles are defaults, never required
   singleton records.

This strategy is intentional for a single-user, local-only application. A
schema change must remain safe to run repeatedly against both an empty database
and an existing production database.

## Rules for schema changes

- Prefer new tables and nullable/defaulted columns.
- Add every new model to `app.models` before `create_all()` runs.
- Add explicit compatibility SQL only when `create_all()` cannot upgrade an
  existing table.
- Treat duplicate-column errors as “already applied”; do not swallow other
  migration failures.
- Add tests for clean bootstrap and upgrade from the oldest supported fixture.
- Create a backup before applying a destructive or data-transforming upgrade.
- Never move desktop financial records into Supabase or another remote store.

## Release verification

For each release candidate:

```bash
GODFIN_TESTING=1 backend/venv/bin/python -m pytest -q \
  backend/tests/test_bootstrap.py backend/tests/test_backup.py
```

Then launch the previous signed build against a synthetic database, upgrade to
the candidate, and verify transactions, encryption, Gmail, license state, and
backup restore.
