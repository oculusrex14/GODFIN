# GODFIN OPUS 4.6 archive evidence

Date: 30 July 2026 (Asia/Kolkata)

## Private archive

- Repository: `oculusrex14/GODFIN-OPUS46-ARCHIVE`
- Visibility: private
- GitHub status: archived/read-only
- Default branch: `main`
- Archive tag: `opus46-deprecated-archive`
- Description: `DEPRECATED — frozen sanitized OG backup; do not develop or release`

## Sanitization and verification

The committed OPUS 4.6 history was copied into an isolated temporary clone and
rewritten before any GitHub push. The rewrite removed Gmail OAuth files,
environment files, key material, databases, backups, financial documents,
logs, generated builds, browser traces, dependency folders, and historical
review output that could repeat sensitive values.

A fresh clone from the private GitHub repository passed:

- Gitleaks 8.30.1 full-history scan: 35 commits scanned, zero findings
- `git fsck --full --strict`
- Sensitive-path audit for OAuth files, databases, backups, logs, PDF files,
  and spreadsheets

## Local cleanup

After the private clone passed all checks, the deprecated source workspace and
its obsolete Claude cache were moved to macOS Trash:

- `GODFIN_OPUS4.6-deprecated-20260730`
- `GODFIN_OPUS4.6-claude-cache-20260730`

The active installation data under
`/Users/oculus/Library/Application Support/GODFIN` was preserved. A verified
SQLite backup was created before production migration work.

## Credential follow-up

The legacy desktop Gmail OAuth client and token values are not present in the
archive. The corresponding Google Cloud credential must remain revoked or be
rotated independently from the website Google OAuth client.

