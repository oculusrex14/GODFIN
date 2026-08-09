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
6. Run the idempotent migration registry again after table creation. This
   installs registry-owned indexes, precision columns, and write guards on a
   fresh database and on any table that did not exist during the pre-create
   pass. The verified recovery point remains the single backup from step 3.
7. Run restart-safe data backfills, then data-only seeds with existence checks.
   Seeds never mutate schema.
8. Record the current revision only after all schema and data work succeeds,
   then verify `quick_check`, foreign keys, revision, and migration
   postconditions before the application becomes available.

Revision 11 is the consolidation boundary for pre-registry private builds. It
absorbs their previously scattered compatibility SQL. All later revisions must
be appended to `MIGRATION_REGISTRY`; no other module may issue upgrade DDL.

Revision 12 installs race-safe identities for global/account monthly
aggregates, global/account recurring patterns, and non-null Gmail message IDs.
It deterministically collapses duplicate derived aggregate/pattern rows while
preserving the strongest linked subscription suggestion. Duplicate Gmail
message identities fail closed because ledger rows are authoritative and must
never be silently deleted by a migration.

Revision 13 begins the exact-money migration at the authoritative ledger edge.
Transactions, transaction splits, and transfer matches retain their legacy
`REAL` amount only as a temporary compatibility shadow; `amount_minor` is the
authoritative integer minor-unit value used by the ORM for reads, comparisons,
ordering, and aggregation. Existing cent-exact rows are backfilled inside the
startup transaction. Ambiguous sub-cent history fails closed instead of being
silently rounded, and restart-safe INSERT/UPDATE guards require the exact and
compatibility shadows to agree.

Revision 14 extends the same invariant to goals, goal contributions and
suggestions, income-source amounts, subscriptions, recurring-pattern amounts,
subscription suggestions, and all monetary monthly-aggregate totals. Nullable
amounts retain exact null parity, signed withdrawals retain their direction,
and atomic aggregate/recurring upserts write both physical columns together.
Historical values must be finite, within range, and cent-exact before any new
column is added.

Revision 15 completes field-specific exact storage for the remaining
net-worth and FX measurements. Holdings quantities and quote unit prices use
eight decimal places, exchange rates use twelve decimal places, and manual or
calculated currency values use integer minor units. Measurements are normalized
once with decimal half-up rounding at their declared scale; historical manual
and calculated money must already be cent-exact and otherwise fails closed.
All authoritative values are stored as scaled SQLite integers while temporary
`REAL`/`NUMERIC` shadows remain synchronized by restart-safe guards. The scales
and supported maxima deliberately keep measurement units below `2**53`, so the
temporary floating compatibility representation cannot lose integer identity.
Compatibility shadows cannot be removed until every supported private build
has crossed the migration boundary.

Revision 16 adds durable recurring-detection provenance. Every stored pattern
now records the exact local transaction IDs used as evidence and the detector
version that interpreted them. Existing patterns receive an empty evidence
array and are repopulated by the next scan. SQLite JSON/version guards reject
malformed provenance on both fresh and upgraded databases.

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

## Authoritative and derived data

Authoritative financial records include transactions, splits, confirmed
transfer links, audit sessions, goal contributions, confirmed subscriptions,
net-worth items and quotes, account routing, settings, and license state. A
migration may validate or backfill these records, but it must not silently pick
one of two conflicting authoritative rows.

Monthly aggregates, recurring patterns, and subscription suggestions are
rebuildable projections. Their database identities are enforced with partial
unique indexes so both account-specific and global (`account_id IS NULL`) rows
remain race-safe. The writers use SQLite conflict handling instead of a
read-then-insert assumption.

`email_message_id` is the authoritative Gmail ingestion identity and is unique
when present. Source and canonical transaction checksums remain indexed but
non-unique: two legitimate transactions may share the current coarse canonical
fingerprint, and statement text can contain repeated identical rows. These
checksums are review/deduplication signals, not safe ledger primary keys.

Fresh databases receive reviewed `CHECK` and foreign-key actions from the ORM
metadata. Older private databases receive equivalent restart-safe write guards
and the revision-12 identity indexes. Remaining historical foreign-key action
normalization requires a later reviewed table-rebuild migration; application
deletion continues to use the centralized dependency order until then.

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
