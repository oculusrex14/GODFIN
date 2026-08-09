# GODFIN local database lifecycle

GODFIN deliberately uses one local SQLite database per desktop profile. It
does not use a hosted application database and it does not maintain an Alembic
revision chain.

## Startup strategy

1. Resolve the database path inside the Electron user-data directory (or the
   configured development path).
2. Read the recorded schema revision. An invalid revision or a revision newer
   than this binary fails closed; GODFIN never attempts an implicit downgrade.
3. Create and verify an online SQLite backup before any older revision is
   upgraded.
4. Run the ordered `MIGRATION_REGISTRY` in one `BEGIN IMMEDIATE` transaction.
   Each revision has an explicit apply function and postcondition validator.
5. Run SQLAlchemy `Base.metadata.create_all()` so a fresh empty profile receives
   every current table, constraint, and index.
6. Run restart-safe data backfills, then data-only seeds with existence checks.
   Seeds never mutate schema.
7. Record the current revision only after all schema and data work succeeds,
   then verify `quick_check`, foreign keys, revision, and migration
   postconditions before the application becomes available.

Revision 11 is the consolidation boundary for pre-registry private builds. It
absorbs their previously scattered compatibility SQL. All later revisions must
be appended to `MIGRATION_REGISTRY`; no other module may issue upgrade DDL.

This strategy is intentional for a packaged, single-user, local-only
application. A schema change must remain safe to run repeatedly against both an
empty database and every supported prior local revision.

## Rules for schema changes

- Prefer new tables and nullable/defaulted columns.
- Add every new model to `app.models` before `create_all()` runs.
- Append one ordered registry revision when existing databases need structural
  or data changes that `create_all()` cannot perform.
- Use schema introspection before DDL and explicit postconditions afterwards.
  Never catch a broad SQL exception and assume work was already applied.
- Keep each revision transactional where SQLite supports it. A failed revision
  must roll back earlier statements and must not advance `schema_revision`.
- Add clean-bootstrap, prior-revision, twice-run idempotency, malformed/future
  revision, interruption/rollback, lock/failure, and postcondition tests.
- Preserve the verified pre-migration backup for release rollback and recovery.
- Never move desktop financial records into Supabase or another remote store.

The retired `backend/alembic` files were removed because production never ran
them and their chain could not bootstrap the current schema. Running Alembic is
not a supported GODFIN operation.

## Release verification

For each release candidate:

```bash
GODFIN_TESTING=1 backend/venv/bin/python -m pytest -q \
  backend/tests/test_bootstrap.py \
  backend/tests/test_startup_migrations.py \
  backend/tests/test_backup.py backend/tests/test_backup_recovery.py
```

Then launch the previous signed build against a synthetic database, upgrade to
the candidate twice, and verify ledger control totals, encrypted values, Gmail
state, license state, settings, and backup restore. Database migration is
forward-only; release rollback restores the verified pre-migration snapshot
before starting an older binary.
