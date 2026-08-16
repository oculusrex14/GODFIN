# GODFIN external release gates

These gates require credentials, provider dashboards, signing identities, qualified review, clean native systems, or owner authority. Code support being complete does not make the gate complete.

| Gate | Owner | Required action | Evidence required | Verification | Code support |
| --- | --- | --- | --- | --- | --- |
| Supabase migration/RLS | Repository owner | Back up the target; apply ordered migrations through `0006`; run pgTAP; test anon, two users, and service role | Migration hashes, function owners/grants, pgTAP output, two-user isolation record | Compare `godfin_migration_evidence` to checked-in manifest | Complete; remote execution pending |
| Cashfree account/KYC | Repository owner | Complete KYC, create separate sandbox/live credentials, approve payment methods and international scope if used | Dashboard status without secrets, merchant account state | One sandbox purchase and later controlled live purchase | Complete; credentials/provider status pending |
| Cashfree webhook | Repository owner | Register `https://godfin.dev/api/webhook`; enable payment, refund/auto-refund, and dispute events | Endpoint/event list, secret masked, delivery IDs | Replay duplicates/out-of-order events and reconcile database state | Complete; provider replay pending |
| Cashfree pricing/tax/refunds | Owner + qualified Indian tax/legal adviser | Approve GST/invoice/refund/international/PPP behavior | Written decision tied to pricing-table version | India/non-India, mismatch, refund, invoice test pack | Fail-closed implementation complete |
| Entitlement signer | Repository owner | Store active Ed25519 private key/version only in protected Vercel secrets | Masked environment names, public-key match, live signed response | Clean package verifies new and overlap signatures | Complete; protected deployment pending |
| Google website OAuth | Repository owner | Configure Web OAuth client for `godfin.dev` and exact Supabase callback; keep scopes to openid/email/profile | Project/client names without secret, callback list | Two-account sign-in/isolation/sign-out test | Website code complete; provider setup pending |
| Gmail public consent | Repository owner | Keep desktop client in Testing while private; before broad release determine Google verification requirements for `gmail.readonly` | Consent-screen status and scope review | Fresh non-owner test only after approval | Private owner OAuth/sync passed |
| Resend and DNS mail | Repository owner | Verify `godfin.dev`; configure `hello@godfin.dev`; publish SPF/DKIM/DMARC | DNS records and Resend verification without secret | Deliver to Gmail plus another provider; test reply path | Fail-closed email code complete |
| Domain/DNS | Repository owner | Point `godfin.dev` and required records to approved services | DNS/HTTPS/redirect evidence | Check canonical, sitemap, robots, 404, HSTS/security headers | Canonical/fallback code complete |
| Apple signing/notarization | Repository owner | Obtain Developer ID Application identity and notarization credentials | Signing identity, notarization ticket, stapled DMG/ZIP | Gatekeeper on clean arm64 and x64 Macs | Workflow/package config complete |
| Windows signing | Repository owner | Obtain Authenticode certificate and protected CI secret | Signature chain/timestamp, installer checksum | Clean Windows 10/11 install and SmartScreen observation | Workflow/package config complete |
| R2 release storage | Repository owner | Configure private immutable release bucket/credentials and protected environments | Bucket policy, object hashes, update metadata | Staged 5/25/50/100 promotion and rollback drill | Workflow contracts complete |
| macOS x64 clean system | Repository owner | Provide native Intel or approved Rosetta matrix | Exact package, logs, checksums, screenshots | Install/upgrade/restore/Ollama/uninstall | Source path complete; execution pending |
| Windows x64 clean system | Repository owner | Provide Windows 10 22H2 and Windows 11 VMs | Exact installer, logs, checksums, screenshots | Complete platform matrix | Source path complete; execution pending |
| Linux x64 clean system | Repository owner | Provide Ubuntu 22.04+ clean VM | Exact AppImage, logs, checksums, screenshots | Complete platform matrix | Source path complete; execution pending |
| Lawful statement corpus | Repository owner | Supply consented/redacted supported-bank variants with all identifiers removed | Corpus provenance and expected control totals | Parser reconciliation/negative corpus on every format | Parser fail-closed behavior complete |
| Browser/accessibility | Repository owner | Review private CI Chromium/Firefox/WebKit results; run native Safari and assistive-technology matrix | Traces/screenshots/axe and manual checklist | Keyboard, zoom, reduced motion, screen readers, auth/payment redirects | CI matrix configured; native/provider checks pending |
| Dependency-license review | Qualified counsel | Review exact SBOM hash, PolyForm distribution, and conditional licenses | Signed clearance tied to version/SBOM hash | Promotion workflow validates clearance record | SBOM/notices/package gates complete |
| Legal/privacy/terms | Qualified Indian counsel + owner | Review product claims, DPDP/privacy, refunds, tax, disclaimer, data pilot, ads | Written approved versions | Compare deployed pages byte-for-byte to approved source | Engineering-aligned draft complete |
| Penetration test | Independent security reviewer | Test local API boundary, Electron, website, auth, licensing, webhooks | Report and closure evidence | Re-test every High/Critical issue | Repository security controls complete |
| Public launch | Repository owner | Give explicit written authorization only after all mandatory gates pass | Dated authorization tied to immutable commit/artifacts | Release checklist fully checked | Intentionally blocked |

## Already completed owner integration

The dedicated desktop Gmail client, owner test-user consent, live OAuth exchange, and first packaged sync are complete for the private owner installation. They are not a substitute for Google consent publication/verification before a broad public release.
