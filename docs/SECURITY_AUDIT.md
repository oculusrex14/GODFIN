# GODFIN dependency security baseline

Baseline date: 2026-07-28

## Shipped dependencies

The release gate checks the dependency sets that are present in the delivered
website and desktop application:

```bash
uv run --with pip-audit==2.10.1 python scripts/audit_python_dependencies.py
cd frontend && npm audit --omit=dev
cd ../website && npm audit --omit=dev
cd ../desktop && npm run audit:prod
```

Current result:

- Python runtime lock: one narrowly accepted, currently unreachable advisory;
  all other known vulnerabilities fail the gate.
- React desktop UI runtime: no known vulnerabilities.
- Next.js website runtime: no known vulnerabilities.
- Electron desktop runtime: no known vulnerabilities.

Both Python lockfiles are generated for Python 3.12 with hashes. CI installs
the runtime lock with `--require-hashes`; release jobs install the build lock
with the same enforcement.

## Temporary cryptography advisory exception

`cryptography==49.0.0` is currently reported under `PYSEC-2026-3552`
(`CVE-2026-69247`, `GHSA-g6cj-pr64-35w5`). The vulnerable behavior is limited
to `pkcs7_decrypt_der`, `pkcs7_decrypt_pem`, and `pkcs7_decrypt_smime` when an
application decrypts attacker-controlled PKCS#7 `EnvelopedData` and exposes an
adaptive response. GODFIN uses Fernet for local secret storage and Ed25519 for
signed model-registry verification; it does not implement PKCS#7 or S/MIME
decryption.

The upstream fix is assigned to `cryptography==50.0.0`, which was not published
on PyPI as of 2026-08-09. Downgrading below the affected range is not acceptable
because those releases carry other known advisories. The repository therefore
uses `scripts/audit_python_dependencies.py` as a fail-closed temporary gate:

- only `PYSEC-2026-3552` is ignored;
- every other `pip-audit` finding remains fatal;
- the exception fails if the locked cryptography version is not exactly
  `49.0.0`;
- the exception fails if any affected decrypt API appears in `backend/app`.

This is a temporary release gate, not a claim that the dependency has no known
vulnerabilities. Remove the exception, update both hashed lockfiles, and rerun
the full backend, encryption, model-registry, packaging, and cross-platform
install matrix as soon as cryptography 50.0.0 or another upstream-fixed release
is available.

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
- Confirm whether cryptography 50.0.0 or another upstream-fixed release is
  available; no public release may silently carry a stale advisory exception.
- Run the backend tests from a fresh environment created from the hashed lock.
- Run the production Playwright smoke test against a new SQLite database.
- Scan the final single-root release history for secrets and real financial
  artifacts.
- Sign and notarize the macOS application after Electron fuses are applied.
- Sign the Windows installer in the build job.
- Keep all generated releases private and draft until owner authorization.
