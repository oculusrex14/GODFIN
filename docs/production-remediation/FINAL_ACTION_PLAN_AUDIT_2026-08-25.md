# Final remediation action-plan audit — 25 August 2026

Source plan:
`GODFIN_CODEX_FINAL_REMEDIATION_ACTION_PLAN_2026-08-25.md`

Exact tested source candidate:
`5ee71fabfe8c7f28726bf625b75801cb254b23a1`

Status vocabulary: `VERIFIED`, `PARTIALLY VERIFIED`, and
`EXTERNAL / NOT EXECUTED`. Source inspection is not counted as execution.

## P0 product defects

| Item | Status | Evidence | Remaining work |
| --- | --- | --- | --- |
| P0.1 PDF parsing and reconciliation | VERIFIED for supplied owner fixtures | SBI 29, HDFC 306, Kotak 497 rows reconcile exactly; strict process/safety, duplicate, overlap, and private-fixture tests are in the 1,011-test suite; `OPENDATALOADER_BENCHMARK.md` records the benchmark rejection | Broader lawful bank-layout corpus remains a release-growth gate |
| P0.2 historical/current actual income | VERIFIED | Dedicated income-history routes/UI and tests cover Jan–Jul ₹34,000, a user-entered August rate, preview/confirmation, semantic income, invalidation, finalization, and reconciliation | Native signed-package interaction remains in the platform matrix |
| P0.3 Budget money patterns | VERIFIED | Budget metrics and cross-view convergence tests pass; plain-language UI is implemented | Native signed-package visual acceptance remains |
| P0.4 CA pack passphrase UX | VERIFIED at source/hosted level | Secure-password generation/copy/disclosure and encrypted tax-pack tests pass | Final native clipboard/assistive-technology acceptance remains |
| P0.5 Gmail Ingest Now | PARTIALLY VERIFIED | Durable ingestion, status, cursor, routing, date-range retry, restart, and trust tests pass | Fresh packaged OAuth, sync, restart/reconnect, and seven-day soak are not executed |
| P0.6 STRIX remediation | PARTIALLY VERIFIED | Security register, exact-source CI, secret scan, parser isolation, local trust, updater, and webhook hardening pass | Credential rotations, independent parser/full pentest, and signed-native retest remain external |
| P0.7 global contrast | PARTIALLY VERIFIED | Static contrast/accessibility contracts and Chromium/Firefox/WebKit matrices pass | Native Safari/Edge and VoiceOver/NVDA/Orca acceptance is not executed |
| P0.8 hardcoded version | VERIFIED | Version/build identity is generated and contract-tested; no public hardcoded `v2.0` remains | Final signed package displays its immutable release version |
| P0.9 every-control acceptance | PARTIALLY VERIFIED | Deterministic inventory records 422 controls in 19 scopes; 390 map to Playwright and 32 are classified manual-native | Mapping is not execution. Final signed-package evidence is attached to 0 controls; exhaustive native/action acceptance remains open |
| P0.10 exact-SHA CI | VERIFIED | GitHub Actions run `32827447450` passed all seven jobs on exact SHA `5ee71fa`; repository was returned to PRIVATE | Rerun after any later application/workflow change |

## P1 release-hardening items

| Item | Status | Evidence | Remaining work |
| --- | --- | --- | --- |
| P1.1 bounded hosted-AI redaction | VERIFIED | Bounded redaction, typed failure, consent, and no-authoritative-total tests pass | Real provider runtime is P1.2 |
| P1.2 real AI-provider acceptance | PARTIALLY VERIFIED | Failure, timeout, malformed-response, consent, catalog, and accepted-provider tests pass; unaccepted hosted providers are hidden | Retain real accepted-provider credentials/response evidence and signed-native Ollama lifecycle |
| P1.3 tier-aware navigation | VERIFIED | Free/Pro/Max visibility and locked-state contracts pass without hiding discoverability | Native visual acceptance remains in P0.9/P1.7 |
| P1.4 Gmail seven-day soak | EXTERNAL / NOT EXECUTED | Automated Gmail contracts pass | Owner must complete fresh packaged authorization, ingest, restart, reconnect, refresh/revocation, and seven-day soak |
| P1.5 Supabase hardening | PARTIALLY VERIFIED | All 11 migrations align remotely; clean CI and linked project each pass 107 assertions for grants, RLS, two users, functions, abuse controls, and commerce state | Managed backup/PITR or approved export, restore drill, leaked-password protection, and real second-account browser flow remain |
| P1.6 Cashfree acceptance | EXTERNAL / NOT EXECUTED | Unit/contracts and linked database state machine pass; checkout stays disabled | KYC, credentials, success/duplicate/refund/dispute/upgrade sandbox matrix, load, tax/refund/PPP approval |
| P1.7 native release matrix | PARTIALLY VERIFIED for exact candidate | Native run `32823401864` built and launched exact SHA `5ee71fa` on macOS arm64, Windows x64, and Linux x64 within startup/memory budgets while preserving the synthetic database and enforcing trust boundaries | Signing/notarization, installers, update/rollback/uninstall, clean owner systems, and R2 remain; macOS x64/Intel is owner-deferred |
| P1.8 regenerate evidence | VERIFIED in this documentation descendant | Central report, matrices, security register, finding register, Supabase evidence, supply-chain record, native JSON evidence, and owner runbook are regenerated from `5ee71fa` and runs `32823401864`/`32827447450` | Regenerate again if application source changes |
| P1.9 qualified reviews | EXTERNAL / NOT EXECUTED | Engineering drafts and fail-closed legal-clearance control exist | Qualified dependency-license, legal/privacy, tax/refund, accessibility, and independent security reviews |

## Definition-of-done decision

The private source candidate is green and merged to `main` for continued
release-candidate work. Apple Silicon, Windows x64, and Linux x64 exact-source
native smoke execution is green; macOS x64/Intel is owner-deferred. It is **not
launch-ready** because P0.9, P1.2, P1.4, P1.5, P1.6, P1.7, and P1.9 retain
explicit external/native acceptance work.

The following remain prohibited until their exact gates close:

- enabling Cashfree checkout or global PPP;
- publishing or promoting installers/update metadata;
- treating the historical ad-hoc macOS package as a customer artifact;
- claiming every-control, signed-platform, Gmail-soak, legal, or pentest pass;
- public launch without written owner authorization tied to immutable artifact
  hashes.

See `EXTERNAL_RELEASE_GATES.md` and
`GODFIN_OWNER_COMPLETION_RUNBOOK.docx` for the beginner-friendly owner steps.
