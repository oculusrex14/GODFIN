# GODFIN migration and rollback procedure

## Scope

The desktop app keeps ordinary user data only in local SQLite. Supabase stores website identity, purchases, licensing, device activations, waitlist data, and provider event state; it never becomes the desktop finance database.

## Local SQLite upgrade

1. Quit all GODFIN processes and confirm no unexpected process owns the database.
2. Identify the exact signed source and target app versions.
3. Start the candidate through its normal Electron launcher. Do not invoke ad-hoc schema SQL.
4. Startup reads `schema_revision`. A malformed or future revision fails closed.
5. Before a required migration, GODFIN creates and verifies an online SQLite recovery point.
6. The ordered registry applies each missing revision in one `BEGIN IMMEDIATE` transaction with explicit preconditions and postconditions.
7. Startup validates `PRAGMA quick_check`, foreign keys, revision, migration postconditions, encrypted data, and financial controls before readiness.
8. A second start must perform no destructive migration and must retain identical controls.

Current local schema revision: 19.

## Required upgrade acceptance

For every supported predecessor/candidate pair:

- preserve a hash and control-total record before upgrade;
- run upgrade twice;
- compare transaction count, debit/credit totals, transfers, goal totals, account mappings, Gmail state, encrypted fields, settings, and license state;
- simulate lock, disk/permission failure, and process interruption;
- verify no failed migration advances the revision;
- preserve the verified pre-migration backup;
- repeat on macOS arm64/x64, Windows x64, and Linux x64.

## Desktop update rollback

Database migration is forward-only. Binary rollback never lets an old build open a newer schema.

1. Before update installation, Electron stops the backend and calls frozen maintenance mode.
2. Maintenance mode creates and validates `backups/update-recovery/snapshots/<from>_to_<to>/...`.
3. It atomically writes a private recovery journal containing the exact version pair, source schema revision, snapshot filename, and SHA-256.
4. Only the exact declared immediate predecessor is eligible for rollback.
5. Before restoring the predecessor snapshot, GODFIN preserves the current database in a separate safety location.
6. If the newer build restarts before installer completion, it restores the preserved current database and marks rollback aborted.
7. If the intended predecessor starts, it marks rollback complete before normal SQLite startup.
8. Missing, altered, mismatched, skipped-version, or incompatible evidence fails closed.

Activity after the pre-upgrade snapshot is retained in the safety backup but is not merged into the older schema automatically.

## Supabase/Cashfree migration

Current ordered website migration boundary: `0006_cashfree_commerce.sql`.

1. Disable checkout, PPP checkout, and public purchase messaging.
2. Export/backup licensing, purchases, activations, payment events, status history, waitlist, and migration evidence.
3. Verify checked-in migration hashes.
4. Run `supabase db reset`, `supabase db lint --local --fail-on error`, and `supabase test db` on a disposable local PostgreSQL/Supabase stack.
5. Apply to a non-production project first.
6. Verify function ownership, empty `search_path`, grants, RLS, two-user isolation, service-role-only mutation, three-device behavior, and fourth-device rejection.
7. Record the exact migration SHA-256 in `godfin_migration_evidence`.
8. Replay Cashfree sandbox success, duplicates, out-of-order refunds, partial/full refunds, and disputes.
9. Reconcile provider IDs, amounts, currency, purchase status, license status, state version, and email idempotency.
10. Repeat the backup and apply to production only after owner approval.

Do not “roll back” commerce by deleting event or purchase history. Disable provider entry points, restore only from a reviewed database backup when necessary, and preserve the event ledger for reconciliation.

## Rollback stop conditions

Stop and preserve evidence if any of the following occurs:

- checksum or manifest mismatch;
- `quick_check` or foreign-key failure;
- control-total mismatch;
- encrypted values cannot be decrypted;
- schema revision is future/unknown;
- provider order/payment cannot be revalidated;
- signing/update metadata is not the reviewed immediate predecessor;
- the verified backup cannot be created or read.
