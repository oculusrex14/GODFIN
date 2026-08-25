# Supabase remote verification evidence — 25 August 2026

This is a secret-free acceptance record for linked project `GODFIN`
(`omrtkfwjauyakhvynutk`, `ap-south-1`). It does not authorize checkout or a
public launch.

## Exact source and hosted CI

- Candidate: `b2dcaeccd237f5ae4e2076ca4959e5e329df72fe`
- Branch: `codex/godfin-production-v6`
- GitHub Actions: `32800966419`
- Result: all seven jobs passed, including the new isolated `supabase-db` job.
- Repository state after CI: `PRIVATE`, verified through the GitHub API.
- Full-history Gitleaks scan before the temporary CI visibility window: 166
  commits and approximately 11.53 MB scanned; no leaks found.

The clean CI database applied all 11 ordered migrations. Its five pgTAP files
passed 107 assertions: 45 RLS/commerce assertions, 13 abuse-control assertions,
26 Cashfree state-machine assertions, 18 upgrade assertions, and 5 email-lease
assertions.

## Defect discovered by the clean database gate

The first new CI run (`32800337862`) proved that a fresh database had correct
own-row policies but lacked explicit `SELECT` grants for the `authenticated`
role. This is why source parsing and a drifted linked project were insufficient
evidence. Migration
`20260825021500_grant_authenticated_rls_reads.sql` now:

- grants `SELECT` only on licenses, purchases, hosted-credit balances, and
  activations;
- leaves authenticated insert, update, and delete denied;
- leaves anonymous reads denied; and
- relies on the existing indexed own-row RLS policies for tenant isolation.

The corrected clean-database CI run passed before remote application.

## Linked-project application

Before the final grant migration, the linked project had all first 10
migrations and an empty purchase table. The final migration was previewed with
`supabase db push --linked --dry-run`, which listed only
`20260825021500_grant_authenticated_rls_reads.sql`. The migration then applied
successfully. A second migration listing showed all 11 local and remote
versions aligned.

All five pgTAP files were executed again against the linked project and passed
the same 107 assertions. The tests run inside transactions and roll back their
synthetic users, purchases, licenses, activations, and events.

## Remaining Supabase gates

- Managed backup history was empty and point-in-time recovery was disabled at
  verification time. The final migration was privilege-only and did not alter
  rows, but backup/PITR and a restore drill remain required before checkout.
- Auth leaked-password protection remains disabled. Enable it in Supabase Auth
  if the project plan supports the feature, then rerun the Auth advisor.
- A real second Google account website sign-in/isolation flow remains a browser
  acceptance item. The database-level two-user isolation test is complete.
- `CHECKOUT_ENABLED` and `PPP_CHECKOUT_ENABLED` remain `false` until Cashfree
  sandbox, refund/dispute, tax, and recovery gates pass.
