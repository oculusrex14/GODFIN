# GODFIN dependency security baseline

Baseline date: 2026-07-28

## Shipped dependencies

The release gate checks the dependency sets that are present in the delivered
website and desktop application:

```bash
uvx pip-audit -r backend/requirements-lock.txt
cd frontend && npm audit --omit=dev
cd ../website && npm audit --omit=dev
cd ../desktop && npm run audit:prod
```

Baseline result:

- Python runtime lock: no known vulnerabilities.
- React desktop UI runtime: no known vulnerabilities.
- Next.js website runtime: no known vulnerabilities.
- Electron desktop runtime: no known vulnerabilities.

Both Python lockfiles are generated for Python 3.12 with hashes. CI installs
the runtime lock with `--require-hashes`; release jobs install the build lock
with the same enforcement.

## Development-only advisories

The Next.js 15 lint stack and Electron Builder 26 packaging stack currently
retain legacy `glob`/`minimatch` dependency branches reported through
`brace-expansion`. They are development dependencies and are not shipped in
the website server bundle or Electron application.

Do not force a global `brace-expansion` override: its current major version
changes the CommonJS export consumed by older `minimatch` releases and breaks
the toolchain. Keep Next.js and Electron Builder on supported versions, audit
the shipped dependency sets as a hard gate, and re-check the full development
tree whenever either toolchain publishes compatible dependency updates.

## Release requirements

- Re-run all four shipped-dependency audits on the release commit.
- Run the backend tests from a fresh environment created from the hashed lock.
- Run the production Playwright smoke test against a new SQLite database.
- Scan the final single-root release history for secrets and real financial
  artifacts.
- Sign and notarize the macOS application after Electron fuses are applied.
- Sign the Windows installer in the build job.
- Keep all generated releases private and draft until owner authorization.
