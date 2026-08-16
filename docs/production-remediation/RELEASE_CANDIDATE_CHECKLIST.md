# GODFIN release-candidate checklist

No checkbox in the public-launch section may be completed by assumption. Attach exact evidence to the immutable candidate.

## Repository and source

- [x] Production repository is private.
- [x] Deprecated archive is private, clearly deprecated, and archived/read-only.
- [x] PolyForm Noncommercial 1.0.0 is the repository license.
- [x] Full-history secret scan passes.
- [x] No database, backup, OAuth credential/token, private statement, real account ending, or generated private log is packaged.
- [x] Stable finding IDs and current dispositions are recorded.
- [ ] Final candidate tag/commit is selected and immutable.

## Deterministic app correctness

- [x] Complete backend regression passes (883 at this evidence point).
- [x] Exact money, shared semantics, finalized periods, parser failure, report reconciliation, transfer, net-worth, subscription, goal, and behavior invariants pass.
- [x] Backup, restore, migration, update-recovery, and destructive-reset tests pass.
- [x] Gmail OAuth/sync/restart tests pass; private owner live OAuth and initial sync pass.
- [x] Frontend lint/build/access-policy contracts pass at the current production baseline.
- [x] Website contracts/lint/build and Cashfree unit tests pass at the current production baseline.
- [x] Desktop privacy/integrity and release/update contract tests pass at the current production baseline.
- [ ] Repeat every automated gate on the exact final commit and retain logs/checksums.

## SQLite and recovery

- [x] Current local schema registry is ordered through revision 19.
- [x] Fresh, upgrade, double-run, malformed/future, lock/failure, integrity, and rollback fixtures pass.
- [x] Isolated owner-database copy migration preserves controls; live database was not used as a test target.
- [ ] Immediate-predecessor signed package upgrades and rolls back on every supported platform.
- [ ] Permission-loss, disk-full, abrupt-kill, and interrupted-restore drills pass on every supported platform.
- [ ] Recovery evidence includes hashes, schema revisions, financial controls, and data preservation.

## Gmail

- [x] Dedicated desktop OAuth client JSON is outside source/package.
- [x] Scope is Gmail readonly.
- [x] Owner is a test user and private installed-app consent succeeds.
- [x] Loopback callback passes OAuth state/PKCE/session binding and does not require the Electron launch secret.
- [x] First live owner sync completes.
- [ ] Decide and document Google verification/publication requirements before non-test users.
- [ ] Run fresh token refresh, revocation, reauthorization, and another native-platform package flow.

## Supabase, Cashfree, and licensing

- [x] Cashfree code uses current provider API, server-side pricing, raw-body signature verification, authoritative re-fetch, and idempotent event state.
- [x] Lifetime Pro/Max include zero hosted-AI credits.
- [x] Signed entitlements bind exact features, state version, installation, issuer/audience, and expiry.
- [x] Three-device logic and deactivation/replacement contracts pass locally.
- [ ] Back up target Supabase and apply migrations through `0006` to a non-production project.
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
- [ ] Configure and test website Google OAuth with exact Supabase callback and two users.
- [ ] Verify `godfin.dev` DNS, HTTPS, redirects, CSP, sitemap, robots, and 404.
- [ ] Verify Resend domain, SPF, DKIM, DMARC, sender, delivery, and reply handling.
- [ ] Review private Chromium/Firefox/WebKit CI results and native Safari behavior.
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
- [ ] Configure protected R2 release environment and immutable storage.
- [ ] Create a private draft release only.
- [ ] Exercise 5%, 25%, 50%, and 100% staged promotion with health review on a private channel.
- [ ] Exercise immediate-predecessor rollback and interrupted rollback.
- [ ] Complete independent penetration test and close findings.
- [ ] Recheck repository privacy and full-history secret scan immediately before tagging.

## Public launch authorization

- [ ] All mandatory items in `EXTERNAL_RELEASE_GATES.md` have retained evidence.
- [ ] No Critical/High residual risk lacks an assigned owner and acceptance record.
- [ ] Qualified legal, privacy, tax, dependency-license, and accessibility reviews are approved.
- [ ] Exact installers are signed, notarized where applicable, checksummed, privacy-inspected, and clean-machine tested.
- [ ] Owner supplies explicit written public-launch authorization tied to the exact commit and artifact hashes.
- [ ] Only after authorization: promote the website, release assets, and update feed.

Current decision: **private release-candidate evaluation only; public launch blocked**.
