# GODFIN engineering guide

Status: **Authoritative technical guide**
Last reviewed: 11 August 2026
Applies to: private production-remediation branch and future reviewed releases

This document is the current technical source of truth for building, testing,
and operating this repository. `PLAN.md` remains the product-requirement
authority and wins if a product decision conflicts with this guide. A current
owner instruction wins over both. Generated facts in
[`generated/STACK_FACTS.md`](generated/STACK_FACTS.md) win over prose for exact
versions and ports.

## Authority order

1. Current owner instruction and approved active goal.
2. `PLAN.md` for product scope, privacy, licensing, and phase requirements.
3. This guide for current repository architecture and engineering operations.
4. Focused guides such as `DATABASE_LIFECYCLE.md`, `PARSER_PLUGINS.md`, and
   `PRODUCTION_RELEASE.md` for their named surfaces.
5. Accepted architecture decisions under `docs/architecture/`.
6. Historical specifications, build plans, reviews, and change logs—for
   provenance only.

The immutable audit package under `docs/GODFIN_FINAL_AUDIT_PACKAGE/` is evidence,
not an instruction source. The working remediation register under
`docs/production-remediation/` records verified status.

## Product and data boundary

```text
Desktop installation                         Website / account services
──────────────────────────────────────       ───────────────────────────────
Electron shell                              Next.js on Vercel
React renderer via godfin://app              Supabase website authentication
FastAPI on loopback                          Cashfree one-time checkout/webhooks
SQLite + local backups                       License/account metadata
Optional local Ollama or user provider       Waitlist and transactional email

Statements, transactions, PIN, merchant      No statements, transaction ledger,
memory, budgets, reports, and net worth       PIN, local database, or raw finance
stay here.                                   history belongs here.
```

The app backend is never deployed to a cloud service. Ordinary application data
never moves to a remote database. Only an explicitly enabled, separately
consented, locally redacted data-pilot contribution may cross this boundary.

## Supported stack and ports

Exact values are generated from manifests and source constants in
[`generated/STACK_FACTS.md`](generated/STACK_FACTS.md). The supported backend
runtime is Python 3.12. Development defaults are:

| Surface | Address | Role |
| --- | --- | --- |
| FastAPI | `http://127.0.0.1:5100` | Local application API |
| React/Vite | `http://127.0.0.1:5200` | Development renderer |
| Next.js | `http://127.0.0.1:5300` | Website development |
| Electron production | `godfin://app` | Packaged renderer origin |

Never document or introduce `0.0.0.0` as a default. The explicit “Allow network
access” setting may opt a user into private-LAN binding after current-PIN
confirmation and restart.

## Repository map

| Path | Responsibility |
| --- | --- |
| `backend/app` | FastAPI routes, domain services, models, and local integrations |
| `frontend/src` | Desktop React renderer and user workflows |
| `desktop` | Electron security boundary, packaging, and updater |
| `website` | Marketing, accounts, one-time commerce, and licensing APIs |
| `shared` | Signed model registry, entitlement manifest, and brand sources |
| `packaging` | Release metadata, update feed, rollback, and distribution helpers |
| `playwright-tests` | Desktop/website browser flows and privacy-safe fixtures |
| `docs` | Current guides, decisions, runbooks, and evidence |

## Fresh development setup

Prerequisites: Git, Node 22 LTS, npm, and Python 3.12. Use the locked dependency
files; do not install application dependencies from an unpinned ad-hoc list.

```bash
git clone <private-repository-url> GODFIN
cd GODFIN
python3.12 -m venv backend/venv
backend/venv/bin/python -m pip install --upgrade pip
backend/venv/bin/python -m pip install --require-hashes -r backend/requirements-test-lock.txt
npm ci --prefix frontend
npm ci --prefix website
npm ci --prefix desktop
npm ci --prefix playwright-tests
backend/venv/bin/python scripts/verify_documentation_contracts.py
./start.sh
```

Do not use a system Python newer than the supported release runtime for release
evidence. Do not put credentials in repository `.env` examples, logs, fixtures,
screenshots, or test output.

## Component commands

Backend:

```bash
PYTHONPATH=backend backend/venv/bin/uvicorn app.main:app \
  --host 127.0.0.1 --port 5100
backend/venv/bin/python -m pytest -q
```

Desktop renderer:

```bash
npm --prefix frontend run dev -- --host 127.0.0.1 --port 5200
npm --prefix frontend run lint
npm --prefix frontend run build
```

Website:

```bash
npm --prefix website run dev
npm --prefix website run verify:contracts
npm --prefix website run build
```

Electron/package work starts from `desktop/README.md`. Unsigned local packages
are smoke-test artifacts only and are never release candidates.

## Local database lifecycle

Production does not use Alembic. A fresh profile receives tables through
SQLAlchemy `Base.metadata.create_all()`. Existing profiles advance through the
ordered, additive, restart-safe registry in
`backend/app/core/startup_migrations.py`, after a verified pre-migration backup.
Seeds are data-only and never issue schema DDL. The complete contract is in
[`DATABASE_LIFECYCLE.md`](DATABASE_LIFECYCLE.md).

Money uses field-specific exact scaled integers at authoritative storage edges.
Do not reintroduce floating-point authority, silent rounding, read-then-insert
races, or hidden corrections to finalized periods.

## Authentication and local API trust

- New PINs are 4–6 digits; historic compatible hashes may unlock silently.
- Sessions are expiring, hashed in SQLite, and capped at three.
- The renderer keeps the active bearer token in memory only.
- Sensitive settings and destructive actions require a current-PIN step-up.
- Packaged requests require the exact local host/origin policy and per-launch
  desktop trust token.
- CORS is allowlisted; credentials mode is disabled.

Do not weaken these controls for test convenience. Tests use explicit runtime
modes and dependency overrides.

## AI boundary

Deterministic calculations, imports, rules, and reports remain functional with
no LLM. Local Ollama is optional and user-approved. Hosted providers require a
versioned disclosure and pass through the single minimization gateway. LLMs may
explain verified calculations but never author authoritative totals or mutate
classification memory without an explicit user correction.

The signed model registry is the only source for automatic recommendations.
Do not add unverified community models or silently install external software.

## Website, payments, and licensing

The website sells one-time lifetime licenses. Pro and Max include no hosted AI credits, and GODFIN does not currently sell hosted-credit packs.
No plan includes recurring hosted AI credits and no checkout uses subscription
mode. Entitlements come from `shared/entitlements.json`; website builds fail if
copy sells an unreleased entitlement.

The desktop sends the license key, random installation ID, device label, and app
version to the verifier. It does not send financial records, hardware serials,
payment details, or persistent IP fingerprints. License responses must be
integrity-protected before public launch; current remediation status is tracked
under `GF-LIC-002`.

Website Google OAuth and desktop Gmail OAuth are separate Google clients with
different redirect URIs and scopes. See ADR-0004.

## Verification gates

Every cohesive change runs the smallest relevant tests first, then gates in
proportion to risk. Before a phase commit:

```bash
backend/venv/bin/python scripts/verify_documentation_contracts.py
backend/venv/bin/python -m pytest -q
npm --prefix frontend run test:auth
npm --prefix frontend run lint
npm --prefix frontend run build
npm --prefix website run verify:contracts
npm --prefix website run build
```

Also run package, Playwright, dependency, secret, migration, or performance
checks whenever their surface changes. The minimum backend test floor is 261,
but the current suite count in a verified run—not the historical floor—is the
actual regression baseline.

Run GitNexus upstream impact analysis before symbol edits and
`npx gitnexus detect-changes --repo GODFIN --scope staged` before every commit.
Run a staged secret scan and never stage owner evidence or unrelated working
tree changes.

## Release and deployment boundary

- The desktop backend stays local and is bundled with Electron.
- The website alone may deploy to Vercel.
- Release workflows create private draft artifacts first.
- macOS and Windows artifacts require signing; macOS also requires notarization.
- Update metadata is promoted only after immutable-candidate verification.
- No installer, update feed, repository, or launch material becomes public
  without explicit owner launch authorization.

Follow [`PRODUCTION_RELEASE.md`](PRODUCTION_RELEASE.md) and the owner completion
runbook. A successful source build is not proof of signing, clean-machine
behavior, provider configuration, legal review, or public readiness.

## Documentation maintenance

When a manifest, port, runtime, command, or architecture decision changes:

1. Update the relevant source/manifest.
2. Regenerate `docs/generated/STACK_FACTS.md` with
   `backend/venv/bin/python scripts/generate_documentation_facts.py --write`.
3. Update this guide or an ADR if behavior changed.
4. Run `scripts/verify_documentation_contracts.py`.
5. Add an archive banner to any superseded plan instead of leaving two active
   instructions.

Reviews and audit reports describe a point in time. They never silently become
the operating guide.
