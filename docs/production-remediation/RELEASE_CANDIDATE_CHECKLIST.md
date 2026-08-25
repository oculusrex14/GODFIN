# GODFIN release-candidate checklist

No checkbox in the public-launch section may be completed by assumption. Attach exact evidence to the immutable candidate.

## Repository and source

- [x] Production repository is private. GitHub API/CLI reported `PRIVATE` on 25 Aug 2026 after exact-candidate CI passed.
- [x] Deprecated archive is private, clearly deprecated, and archived/read-only.
- [x] PolyForm Noncommercial 1.0.0 is the repository license.
- [x] Full-history secret scan passes.
- [x] No database, backup, OAuth credential/token, private statement, real account ending, or generated private log is packaged.
- [x] Stable finding IDs and current dispositions are recorded.
- [ ] Final candidate tag/commit is selected and immutable.

## Deterministic app correctness

- [x] Complete backend regression passes (all 1,008 in GitHub Actions run `32787609617` on exact application-code candidate `3a26090`).
- [x] Exact money, shared semantics, finalized periods, parser failure, report reconciliation, transfer, net-worth, subscription, goal, and behavior invariants pass.
- [x] Backup, restore, migration, update-recovery, and destructive-reset tests pass.
- [x] Gmail OAuth/state/trust/sync/restart automated tests pass.
- [ ] Fresh owner OAuth, first sync, restart, disconnect/reconnect, and seven-day soak pass on a package built from `3a26090` or a documentation-only descendant.
- [x] Frontend lint/build/access-policy contracts pass at the current production baseline.
- [x] Website contracts/lint/build and Cashfree unit tests pass at the current production baseline.
- [x] Desktop privacy/integrity and release/update contract tests pass at the current production baseline.
- [x] Every source-level automated gate passed on exact application-code commit `3a26090`; run URL and job results are retained.

## SQLite and recovery

- [x] Current local schema registry is ordered through revision 22.
- [x] Fresh, upgrade, double-run, malformed/future, lock/failure, integrity, and rollback fixtures pass.
- [x] Isolated owner-database copy migration preserves controls; live database was not used as a test target.
- [ ] Immediate-predecessor signed package upgrades and rolls back on every supported platform.
- [ ] Permission-loss, disk-full, abrupt-kill, and interrupted-restore drills pass on every supported platform.
- [ ] Recovery evidence includes hashes, schema revisions, financial controls, and data preservation.

## Gmail

- [x] Dedicated desktop OAuth client JSON is outside source/package.
- [x] Scope is Gmail readonly.
- [x] Both owner addresses are listed as Google test users.
- [x] Automated callback contracts pass signed state, nonce, expiry, single-use, launch binding, and exact loopback validation.
- [ ] Fresh installed-candidate consent and first live sync complete without `MISSING_LAUNCH_TRUST`.
- [ ] Decide and document Google verification/publication requirements before non-test users.
- [ ] Run fresh token refresh, revocation, reauthorization, and another native-platform package flow.

## Supabase, Cashfree, and licensing

- [x] Cashfree code uses current provider API, server-side pricing, raw-body signature verification, authoritative re-fetch, and idempotent event state.
- [x] Lifetime Pro/Max include zero hosted-AI credits.
- [x] Signed entitlements bind exact features, state version, installation, issuer/audience, and expiry.
- [x] Three-device logic and deactivation/replacement contracts pass locally.
- [ ] Back up target Supabase and apply all 10 ordered migrations through `20260824211115_cashfree_email_delivery_claim.sql` to a non-production project.
- [ ] Run PostgreSQL pgTAP/RLS/function-owner/two-user/service-role matrix.
- [ ] Complete Cashfree KYC and separate sandbox/live secret configuration.
- [ ] Replay success, duplicate, out-of-order refund, partial/full refund, and dispute events.
- [ ] Verify suspended/revoked license removes paid access at next online check.
- [ ] Obtain qualified GST/invoice/refund/international/PPP approval.
- [ ] Keep `CHECKOUT_ENABLED` and `PPP_CHECKOUT_ENABLED` false until every item above passes.

## Website, identity, domain, and mail

- [x] Canonical source configuration uses `godfin.dev`; Vercel deployment fallback remains available.
- [x] General contact defaults to `hello@godfin.dev`.
- [x] App/website entitlement manifest rejects unreleased feature claims.
- [x] Three-engine Playwright CI matrix is configured.
- [x] GitHub Actions run `32787609617` completed successfully with all six required jobs on exact SHA `3a26090`.
- [x] Website Google OAuth is configured with the exact Supabase callback and the owner account returns to `/account`.
- [ ] Repeat website Google OAuth with a distinct second user and retain account-isolation evidence.
- [x] `godfin.dev` DNS, HTTPS, apex/`www` redirects, CSP, sitemap, robots, and checkout safe-disable behavior are verified on the currently deployed older website.
- [ ] Repeat domain/security-header acceptance after deploying the exact final website SHA.
- [ ] Verify Resend domain, SPF, DKIM, DMARC, sender, delivery, and reply handling.
- [x] Review private Chromium/Firefox/WebKit CI results; all hosted suites passed on exact SHA `3a26090`.
- [ ] Review native Safari behavior and manual assistive-technology flows on a signed candidate.
- [ ] Obtain qualified legal/privacy/terms/accessibility review of exact deployed pages.

## Desktop packages

- [x] Private macOS arm64 ad-hoc candidate passes package privacy, data preservation, loopback trust, and maintenance boundaries.
- [ ] Rebuild macOS arm64 from the exact final commit.
- [ ] Build and run macOS x64, Windows x64, and Linux x64 exact artifacts.
- [ ] Sign/notarize macOS artifacts and verify Gatekeeper on clean systems.
- [ ] Sign Windows installer and record SmartScreen behavior on clean Windows 10/11.
- [ ] Launch Linux AppImage on Ubuntu 22.04+ with secure-storage fallback documented.
- [ ] Verify install, first run, upgrade, rollback, uninstall, reinstall, and data preservation on each platform.
- [ ] Verify official Ollama install/detect/download/cancel/crash/digest/benchmark/remove lifecycle on each supported platform.
- [ ] Generate checksums, blockmaps/update metadata, SBOM, notices, and provenance for exact bytes.

## Release operations

- [x] Release, promotion, and rollback workflows use pinned actions and protected confirmation gates.
- [x] Public promotion requires exact legal-clearance/SBOM evidence.
- [x] Confirm GitHub Actions jobs start and complete: run `32787609617` passed all six jobs on exact SHA `3a26090`.
- [ ] Configure protected R2 release environment and immutable storage.
- [ ] Create a private draft release only.
- [ ] Exercise 5%, 25%, 50%, and 100% staged promotion with health review on a private channel.
- [ ] Exercise immediate-predecessor rollback and interrupted rollback.
- [ ] Complete independent penetration test and close findings.
- [x] Change `oculusrex14/GODFIN` back to PRIVATE and verify through the GitHub API after exact-source CI.
- [ ] Recheck repository privacy and the full-history secret scan immediately before tagging.

## Public launch authorization

- [ ] All mandatory items in `EXTERNAL_RELEASE_GATES.md` have retained evidence.
- [ ] No Critical/High residual risk lacks an assigned owner and acceptance record.
- [ ] Qualified legal, privacy, tax, dependency-license, and accessibility reviews are approved.
- [ ] Exact installers are signed, notarized where applicable, checksummed, privacy-inspected, and clean-machine tested.
- [ ] Owner supplies explicit written public-launch authorization tied to the exact commit and artifact hashes.
- [ ] Only after authorization: promote the website, release assets, and update feed.

Current decision: **private release-candidate evaluation only; public launch blocked**.
