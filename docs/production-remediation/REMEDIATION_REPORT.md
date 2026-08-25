# GODFIN production remediation report

Evidence date: 25 August 2026 (Asia/Kolkata)

## Verdict

GODFIN is a private release candidate, not an authorized public release. The
repository has no unclassified or `Open` finding. The current register contains
67 findings: 31 `Verified` and 36 `Partially verified` after closure of the
Supabase database/RLS finding.

The defensible readiness statement is:

> Application source, deterministic finance behavior, hosted CI, clean and
> linked Supabase migration/RLS execution, repository privacy, and exact-source
> native unpacked smoke execution on Apple Silicon, Windows x64, and Linux x64
> are verified. Payment-provider, Gmail-soak, signed-installer,
> independent-review, recovery, and explicit launch-authority gates remain.

Public launch, checkout enablement, installer publication, and update-feed
promotion remain unauthorized.

## Candidate identity

- Starting remediation source: `5900e984e516b181ce98475261349a7187d621b4`
- Exact application source candidate: `5ee71fabfe8c7f28726bf625b75801cb254b23a1`
- Branch: `codex/godfin-production-v6`
- Remote: private `oculusrex14/GODFIN`
- Host evidence: macOS arm64, Python 3.12.13
- Backend baseline: 327 tests
- Current backend: 1,011 tests
- Hosted `main` CI: run `32827447450`, all seven jobs passed
- Native smoke CI: run `32823401864`; macOS arm64, Windows x64, and Linux x64 passed
- Audit sources: current records under `docs/production-remediation/`

The finding register remains authoritative for stable IDs, implementation
history, residual risk, and assignment. This report records the latest
candidate-wide evidence.

## Current architecture and controls

### Financial correctness

- Shared transaction semantics consistently exclude confirmed transfers,
  reversals, refunds, reimbursements, and non-income credits from authoritative
  totals.
- Finalized periods are protected at every current ingress path.
- Monetary values use exact integer minor units or field-specific scaled
  integers with Decimal-facing ORM behavior.
- Golden-ledger acceptance uses an independent standard-library oracle for
  dashboard, cash flow, reports, CA pack, income, subscriptions, goals, net
  worth, audit, and AI non-authority controls.
- Owner-supplied private PDFs reconcile exactly to SBI 29, HDFC 306, and Kotak
  497 rows; only hashes and aggregates are retained as evidence.

### Local data lifecycle

- The ordered SQLite registry is current through revision 22.
- Migrations are additive, restart-safe, preconditioned, postconditioned, and
  preceded by a verified online backup.
- Restore validates a staged candidate before replacement and preserves the
  failed active database.
- Binary rollback is bound to the immediate predecessor and its exact recovery
  journal; older builds fail closed on newer schemas.

### Authentication, local boundary, and privacy

- PIN verification uses durable device/IP throttling, versioned PBKDF2,
  rehash-on-success, weak-PIN rejection, and a separate random encryption key.
- Renderer bearer state is memory-only and legacy stored tokens are removed.
- Packaged FastAPI is loopback-only by default, accepts the exact trusted app
  origin, and requires the Electron per-launch secret.
- Hosted-AI consent, minimization, redaction, typed results, taxonomy
  validation, and non-authoritative explanation boundaries are centralized.
- Ordinary financial data remains in local SQLite.

### Gmail

- Installed-app OAuth uses fixed loopback callback, signed random single-use
  state, launch binding, PKCE, expiry, and private atomic token storage.
- Pagination, cursor safety, idempotency, partial failure, refresh/revocation,
  durable jobs, and Gmail-only deletion are automated.
- Historical owner OAuth/sync evidence exists. A fresh packaged-candidate
  connection, restart, reconnect, and seven-day soak remain mandatory.

### Licensing, commerce, and website

- Paid access requires a versioned Ed25519 entitlement bound to the random
  installation ID and the released feature manifest.
- Three-device enforcement and deactivation remain server-authoritative.
- Cashfree replaced Stripe. Server-owned prices, bounded raw-body HMAC,
  authoritative provider re-fetch, idempotent event state, refunds, disputes,
  and in-place lifetime upgrades are implemented.
- Pro and Max are lifetime purchases and include zero recurring hosted-AI
  credits. Checkout and PPP stay fail-closed.
- Canonical website configuration is `https://godfin.dev`; the Vercel domain is
  the fallback and `hello@godfin.dev` is the public contact.

### Supabase database closure

- All 11 ordered migrations through
  `20260825021500_grant_authenticated_rls_reads.sql` align on the linked project.
- A clean CI database and the linked project each pass all 107 pgTAP assertions.
- Assertions cover anon/authenticated/service-role grants, two-user own-row
  isolation, SECURITY DEFINER execution boundaries, device caps, abuse limits,
  Cashfree ordering/refund/dispute state, upgrades, and email leasing.
- The clean database gate found and prevented a missing authenticated `SELECT`
  grant. The additive fix grants read-only access on the four own-row account
  tables while keeping anonymous and authenticated writes denied.
- Managed backup/PITR, a restore drill, Auth leaked-password protection, and a
  real second-account browser flow remain release gates.

### UX, AI, jobs, performance, and release

- Shared dialog/focus, skip-link, live-region, reduced-motion, accessible-label,
  information-bubble, and destructive-recovery contracts are implemented.
- Local-model registry digests are signed and fail closed; model work is
  cancellable, resource-checked, and never authoritative for finance totals.
- Durable SQLite jobs use atomic claims, leases, heartbeats, retry/backoff,
  bounded concurrency, cancellation, and restart recovery.
- Performance budgets are executable; 100,000-row dashboard and report paths
  remain within their recorded arm64 baseline.
- Release workflows pin actions, verify package privacy, and bind exact bytes to
  checksums, SBOM, notices, and provenance.

## Verification snapshot

| Surface | Current result |
| --- | --- |
| Backend | 1,011 passed on exact SHA `5ee71fa` |
| Frontend | lint, accessibility/content/auth contracts, controls, and Vite build passed |
| Website | contracts, 11 unit tests, migration hashes, Next.js build, and audit passed |
| Browser/e2e | production smoke and Chromium/Firefox/WebKit matrices passed |
| Supabase clean DB | 11 migrations and 107 pgTAP assertions passed |
| Supabase linked DB | 11 migrations aligned and 107 pgTAP assertions passed |
| Desktop source audit | privacy/integrity, update/release, dependency audit, and syntax passed |
| Secret scanning | complete Git history passed before temporary CI visibility |
| Dependency audits | Python and npm surfaces report no accepted vulnerability; cryptography is on fixed 50.x |
| Repository visibility | GitHub API reports `PRIVATE` after run `32827447450` |
| macOS arm64 exact-source package smoke | passed: 2.098 s first start, 2.440 s restart, 529.2 MB, database preserved, boundaries enforced |
| Windows x64 exact-source package smoke | passed: 3.886 s first start, 2.390 s restart, 488.1 MB, database preserved, boundaries enforced |
| Linux x64 exact-source package smoke | passed: 3.224 s first start, 2.360 s restart, 498.5 MB, database preserved, boundaries enforced |
| macOS x64/Intel | owner-deferred; no support/release claim is made |

## Residual release blockers

- Supabase backup/PITR/restore evidence and leaked-password protection.
- Cashfree KYC, credentials, purchase/refund/dispute/upgrade sandbox matrix, and
  qualified tax/refund/PPP decisions.
- Fresh packaged Gmail OAuth/restart/reconnect and seven-day soak.
- Resend domain and SPF/DKIM/DMARC/delivery evidence.
- Signed/notarized macOS arm64, Authenticode Windows, Linux installer, clean
  install/update/rollback/uninstall, and R2 staged-update evidence.
- macOS x64/Intel validation before any future Intel support claim; explicitly
  deferred by the owner for this pass.
- Native assistive-technology and every-control signed-package acceptance.
- Qualified dependency-license, legal/privacy, tax, and accessibility review.
- Independent parser fuzzing and full penetration test.
- Explicit written public-launch authorization tied to immutable artifacts.

## Final recommendation

Keep the repository, releases, checkout, and update channel private/disabled.
Use application candidate `5ee71fa` only for private release-candidate
evaluation. Complete
the assigned external gates in `EXTERNAL_RELEASE_GATES.md` and the owner
runbook. No source-level success is a substitute for provider, signed-package,
qualified-review, or owner-launch evidence.
