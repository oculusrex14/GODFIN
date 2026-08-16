# GODFIN Production Remediation Baseline

Recorded: 2 August 2026 (Asia/Kolkata)

## Repository state

- Repository: private `oculusrex14/GODFIN`
- Branch: `codex/godfin-production-v5` (already a dedicated production-remediation branch)
- Starting commit: `5900e984e516b181ce98475261349a7187d621b4`
- Audit snapshot: `81e160338d5137084c7b6b2721f2780634d62b98`
- Working tree before remediation contained only owner-provided untracked evidence:
  - `GODFIN_CODEX_PRODUCTION_REMEDIATION_GOAL.md`
  - `docs/CODEBASE_REVIEW_2026-07-30.md`
  - `docs/GODFIN_FINAL_AUDIT_PACKAGE/`
- No existing user work was discarded, reset, cleaned, or overwritten.

## Environment

- Host: Apple Silicon (`arm64`)
- OS: macOS 26.5.2 (Darwin 25.5.0)
- Locked backend runtime: Python 3.12.13 at `backend/venv/bin/python`
- Default system Python: 3.14.4 (not used for the baseline backend suite)
- Node.js: 25.8.2
- npm: 11.11.1
- Git: 2.53.0
- Playwright CLI: 1.62.1
- Supabase CLI: 2.110.0
- Vercel CLI: 58.1.0
- GitNexus index refreshed at starting commit: 8,521 nodes, 16,731 edges, 296 clusters, 300 flows
- Free disk at baseline: approximately 48 GiB

## Audit evidence integrity

The supplied checksum manifest contains absolute `/mnt/data/...` paths, so a direct `shasum -c` is not portable and reports missing files. Verification by manifest basename succeeded for all six protected artifacts:

- `GODFIN_PRODUCTION_READINESS_AUDIT_FINAL.md`
- `GODFIN_PRODUCTION_READINESS_AUDIT_FINAL.docx`
- `GODFIN_FINDINGS_REGISTER.csv`
- `GODFIN_REPOSITORY_COVERAGE.csv`
- `GODFIN_API_ROUTE_MATRIX.csv`
- `GODFIN_AUDIT_SUMMARY.json`

The audit package is treated as immutable evidence and will not be edited.

## Baseline verification

| Surface | Command | Result | Duration/evidence |
| --- | --- | --- | --- |
| Backend | `backend/venv/bin/python -m pytest -q` from `backend/` | Passed: 327 tests | 10.16 s |
| Frontend lint | `npm run lint` from `frontend/` | Passed | Combined with build |
| Frontend build | `npm run build` from `frontend/` | Passed: Vite 7.3.6, 3,417 modules | 2.36 s |
| Website contracts | `npm run verify:contracts` from `website/` | Passed | Lifetime payment, entitlement, PPP, licensing, and waitlist contracts |
| Website build | `npm run build` from `website/` | Passed: Next.js 15.5.22, 21 pages/routes generated | Build/type checks completed |
| Desktop privacy tests | `npm run test:privacy` from `desktop/` | Passed: 2 tests | 84 ms |

This baseline is evidence of the current test state only. It does not close any audit finding whose acceptance criteria are not covered by those tests.

## Available and unavailable external capability

Available:

- Local Python 3.12 production-compatible environment with real Gmail, PDF, XLS, and XLSX libraries installed.
- Existing Supabase and Vercel CLIs.
- Existing private GitHub remote.
- Existing website deployment configuration and a Vercel OIDC value in the ignored local website environment.

Unavailable or not configured at baseline:

- Dedicated desktop Gmail Google OAuth client JSON.
- Stored Gmail OAuth token for this installation.
- `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` process environment values.
- Google Cloud CLI.
- macOS code-signing identity (`security find-identity` reported zero valid identities).
- Windows signing certificate and native Windows host.
- Linux native host/package execution evidence.
- Production Cashfree, production Google OAuth publication/verification, Resend/DNS, notarization, legal/privacy/tax review, and public-launch evidence are not assumed merely because source support exists.

## Platform limitations

- macOS arm64 is the only platform that can be built and executed natively on this host.
- macOS x64 can be configured or cross-built where tooling permits, but cannot be claimed as launched without x64/Rosetta execution evidence.
- Windows x64 and Linux x64 require native CI runners or clean VMs for defensible launch evidence.
- Signing and notarization remain external gates until identities and provider-side evidence exist.

## Current audit reconciliation

- Primary findings: 54 (2 Critical, 27 High, 23 Medium, 1 Low, 1 Informational).
- Supplemental validated findings to add: 8 (4 High and 4 Medium).
- No finding is marked `Verified` at baseline solely because existing tests pass.
- Strong controls to preserve: Electron isolation, hashed expiring sessions, encryption-key fail-closed behavior, Cashfree raw-body signature verification, Supabase RLS source design, hash-pinned dependency intent, and controlled release-promotion workflows.
- The immediate Gmail UI error is confirmed to represent a missing external desktop OAuth client, not a frontend rendering failure. Repository OAuth and synchronization defects remain independently actionable under `GF-OAUTH-001`, `GF-GMAIL-001`, `GF-GMAIL-002`, and `GF-GMAIL-003`.

## Baseline verdict

The audited starting state is **not ready for public production**. The baseline is suitable for remediation because all existing local automated checks pass and the user evidence has been preserved.
