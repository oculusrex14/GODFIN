# GODFIN verification matrix

This matrix records the current executable evidence. “Not executed” is never treated as passed.

| Domain | Command/evidence | Current result | Remaining limitation |
| --- | --- | --- | --- |
| Backend regression | GitHub Actions run `32800966419`, backend job | Passed: all 1,008 on exact SHA `b2dcaeccd237f5ae4e2076ca4959e5e329df72fe` | Native packaged execution is separate |
| Gmail/parser/routing/restart | Focused Gmail service, email parser, and ingestion suites | Passed: 97, including stored-expiry reload after restart | Older unmatched mail requires an explicit date-range retry |
| Financial/migration/recovery | Exact money, parser safety, restore, relationships, startup migrations | Passed in current backend suite; isolated owner-copy migration clean | Windows/Linux/native interruption drills pending |
| API access policy | `python scripts/verify_api_access_policy.py` and contract tests | Passed at current production baseline | Browser rendering checked separately |
| Test governance | `python scripts/verify_test_governance.py` | Passed at current production baseline | Selective mutation execution remains optional follow-up |
| Performance contract | `python scripts/verify_performance_contract.py` plus synthetic ledger suite | Passed; 100k dashboard 327.31 ms, report 339.24 ms | Minimum Windows/Linux hardware pending |
| Golden-ledger oracle | `backend/tests/test_golden_ledger_acceptance.py` using `golden_ledger_oracle.py` | Passed independently expected dashboard, cash flow, reports, CA pack, income, subscriptions, goals, net worth, audit, and AI non-authority controls | Native packaged execution is separate |
| Private statement fixtures | `scripts/verify_private_statement_fixture.py` against owner PDFs | Passed exact reconciliation: SBI 29, HDFC 306, Kotak 497 rows | Files remain private and are not repository fixtures |
| Frontend lint | `npm run lint` in `frontend` and GitHub Actions run `32800966419` | Passed on exact SHA `b2dcaec` | None for source lint |
| Frontend accessibility contract | `npm run verify:a11y` in `frontend` | Passed: 187 buttons, 88 raw fields, 26 dialogs, semantic contrast contract | Manual assistive-technology matrix pending |
| Frontend auth/content contracts | `npm run test:auth && npm run test:content` in `frontend` | Passed: 1 auth and 8 content tests | Native reload/relaunch interaction pending |
| Frontend build/control inventory | `npm run build && npm run verify:controls` in `frontend` | Passed; 422 controls across 19 route scopes | Native signed-package pixel inspection pending |
| Website Cashfree unit tests | `npm run test:cashfree` in `website` | Passed: 5 | Cashfree sandbox/live pending |
| Website webhook security | `npm run test:webhook` in `website` | Passed: 3 bounded raw-body/UTF-8 tests | Provider replay/load acceptance pending |
| Website lifetime upgrades | `npm run test:upgrades` in `website` | Passed: 3 | Cashfree sandbox/provider acceptance pending |
| Website production contracts | `npm run verify:contracts` in `website` | Passed | Deployed environment and qualified policy review pending |
| Website lint/build | `npm run lint && npm run build` in `website` | Passed at current production baseline | Production deployment intentionally not promoted with Cashfree enabled |
| Website browser matrix | GitHub Actions run `32800966419`, `website-browser-matrix` job | Passed across Chromium, Firefox, and WebKit on exact SHA `b2dcaec` | Native Safari and live provider flows remain pending |
| Hosted CI | GitHub Actions run `32800966419` | Passed: all seven jobs on exact SHA `b2dcaec`, including backend, frontend, website, browser/e2e, desktop audit, and Supabase DB | Any later code change requires a new exact-SHA run |
| Supabase migration manifest | `npm run verify:migrations` in `website` | Passed: 11 ordered hashes through `20260825021500_grant_authenticated_rls_reads.sql`; all 11 aligned remotely | Backup/PITR and restore drill remain pending |
| Supabase database/RLS | CI `supabase-db` job plus linked-project `supabase db query` runs | Passed: clean and linked databases each passed all 107 pgTAP assertions, including anon/authenticated/service-role and two-user isolation | HIBP Auth protection and real second-account browser flow remain pending |
| Desktop privacy/integrity | `npm run test:privacy` in `desktop` | Passed: 11 at current production baseline | Other native package formats pending |
| Update/release contracts | `npm run test:update` and packaging tests | Passed: 12 at current production baseline | Signed updater/R2 staged drills pending |
| macOS arm64 package | `docs/production-remediation/evidence/macos-arm64-package-0.1.0-ea76be1.json` | Passed private ad-hoc package/privacy/data-preservation checks; corrected Gmail-restart build installed with backend auto-start verified | Not notarized; Gatekeeper correctly rejects public use |
| Python dependency audit | pip-audit 2.10.1 over runtime/test/build locks | Passed: no known vulnerabilities; cryptography is on the fixed 50.x line and no exception remains | Repeat on final immutable candidate |
| npm production audits | frontend/website/desktop locked sets | Passed, no known production vulnerabilities | Repeat on final immutable candidate |
| SBOM/notices | supply-chain verifier and package byte comparison | Passed: 1,035-component current SBOM evidence | Qualified license review pending |
| Secret scan | staged plus full Git history | Passed; no leaks | Repeat immediately before candidate tag |
| Repository privacy | GitHub API/CLI check after run `32800966419` | Passed: `oculusrex14/GODFIN` reports `PRIVATE` on 25 Aug 2026 | Recheck immediately before any private tag or draft-release action |
| Gmail live owner flow | owner-reported OAuth attempt plus candidate trust tests | **Not closed:** prior installed build returned `MISSING_LAUNCH_TRUST`; candidate code is fixed but not packaged/soaked | Fresh package, authorization, initial sync, restart, reconnect, and seven-day soak pending |
| Cashfree sandbox | Provider dashboard/API | Not executed | Credentials/KYC and owner provider work required |
| macOS x64 | Native build/launch/update/restore | Not executed | Clean Intel/Rosetta test system and signing identity required |
| Windows x64 | Native installer/launch/update/restore | Not executed | Clean Windows VM and Authenticode identity required |
| Linux x64 | Native AppImage/launch/update/restore | Not executed | Clean Ubuntu 22.04+ system required |
