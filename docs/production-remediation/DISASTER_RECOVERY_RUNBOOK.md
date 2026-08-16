# GODFIN disaster recovery runbook

## First response

1. Quit GODFIN. Do not repeatedly reopen it if corruption, migration failure, or wrong totals are suspected.
2. Preserve the entire GODFIN Application Support directory and note the app version, OS, time, and visible support request ID.
3. Do not share the database, OAuth JSON/token, encryption key, logs, statements, or financial screenshots in public support channels.
4. Work on copies. Never test recovery against the only active database.

## Restore through the app

1. Open Settings → Backup & Export → Recent backups.
2. Select a verified backup from GODFIN's allowlisted backup directory.
3. Enter the current PIN and confirm the exact restore intent.
4. Electron stops the backend and executes maintenance mode; the renderer cannot replace the database directly.
5. GODFIN creates a new recovery point of the current database before staging the selected backup.
6. The candidate is validated in a separate temporary database for integrity, foreign keys, supported schema, financial controls, encrypted values, protected settings, and license state.
7. Only a valid candidate atomically replaces the active database.
8. After restart, verify account list, month totals, recent transactions, goals, backups, Gmail state, and license tier.

## Automatic failure behavior

- A corrupt, altered, missing-manifest, expired-request, replayed-request, cross-installation, path-traversal, wrong-control-total, wrong-encryption, wrong-settings, or wrong-license backup is rejected.
- A post-replacement validation failure automatically restores the preserved active database.
- A failed destructive operation never continues when its promised backup fails.
- The failed/candidate databases remain available for owner-controlled forensic recovery rather than being silently deleted.

## Manual owner escalation

If the app cannot start:

1. Make a filesystem copy of the complete Application Support directory.
2. Record SHA-256 hashes of `godfin.db`, candidate backups, manifests, and the installed app—never their contents.
3. Confirm the installed app version and whether an `update-recovery.json` journal exists.
4. Use only the matching frozen backend maintenance command documented for that version; do not run arbitrary SQLite edits.
5. If an update journal is valid, follow `MIGRATION_AND_ROLLBACK.md` for abort/completion behavior.
6. If no verified candidate passes, retain all copies and escalate to a private qualified recovery engineer. Do not fabricate totals or import the damaged database into production.

## Recovery verification checklist

- `PRAGMA quick_check` is `ok`.
- `PRAGMA foreign_key_check` returns no rows.
- Schema revision is supported by the running binary.
- Transaction count and debit/credit/transfer control totals match the selected backup manifest.
- Encrypted settings and credentials decrypt without being printed.
- PIN/session behavior is correct; old sessions are not trusted after PIN change.
- Account routing, finalized periods, goal contribution ledger, subscriptions, net worth, and recurring state are coherent.
- Gmail token health is actionable; no sync cursor advanced because of a partial restore/sync.
- Signed license state matches the selected installation and authoritative server when online.
- A new verified backup can be created after recovery.

## Cross-platform release drill

Before launch, perform corrupt-backup, permission-loss, disk-full, process-kill, interrupted replacement, update rollback, uninstall/reinstall, and power-loss simulations on clean macOS arm64/x64, Windows x64, and Linux x64 systems. Retain secret-free hashes, versions, timings, statuses, and screenshots.
