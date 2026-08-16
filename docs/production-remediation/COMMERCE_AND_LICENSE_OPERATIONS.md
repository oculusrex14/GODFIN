# Commerce and License Operations

This document is the secret-free operating contract for GODFIN lifetime
licenses. It does not authorize a public launch. Provider setup and production
tests remain release gates.

## Authority boundaries

- The desktop app trusts paid access only when an Ed25519 entitlement envelope
  verifies against a public key bundled with the backend.
- The signed claims bind the license to a random installation ID. GODFIN does
  not use hardware serial numbers, payment details, or persistent IP
  fingerprints for device identity.
- Supabase is authoritative for license status and the three-active-device
  limit. The app's local `license_tier`, `license_status`, and verification-date
  settings are compatibility/display fields and cannot enable a paid feature.
- Cashfree is authoritative for payment, refund, and dispute events. Only a
  signature-verified webhook may call the service-role provisioning and payment
  reconciliation functions.
- Ordinary finance data remains in local SQLite and is never part of the
  website license request.

## Signed entitlement lifecycle

1. The website hashes the submitted license key and random installation ID.
2. Supabase verifies that the license is active and creates or refreshes one of
   at most three active installation records.
3. The website signs the exact released feature list, tier, license ID,
   installation hash, entitlement-manifest version, license-state version,
   issue time, expiry time, and a unique token ID.
4. The desktop verifies the signature before parsing or trusting claims. It
   also verifies issuer, audience, feature equality, installation binding,
   timestamps, state version, and key status.
5. Invalid, modified, future-dated, expired, wrong-installation, oversized, or
   unknown-key envelopes fail closed to Core.

The configured default lifetime is seven days. The verifier enforces an
absolute maximum of 31 days. A valid cached envelope therefore permits paid
features while offline until its expiry. A refund, dispute, account-side device
deactivation, or emergency key retirement cannot be learned by an offline app
until it next verifies or the cached envelope expires. This residual grace is a
deliberate availability trade-off, not a claim of unbreakable DRM.

## Signing-key rotation

Private signing keys must remain outside the repository, local backups, build
artifacts, logs, screenshots, and owner documents.

Normal rotation order:

1. Generate a new Ed25519 pair with
   `website/scripts/generate-entitlement-keypair.mjs`, passing a private output
   path outside the repository and the shared public-manifest path.
2. Keep the prior public key at `overlap`. Commit and ship the public manifest
   in a private desktop update before the server signs with the new key.
3. Add the new private key to the protected Vercel environment value and set
   its version as active. Do not print the value to a terminal transcript.
4. Verify a newly signed response on a clean packaged app and verify an
   existing cached response signed by the overlap key.
5. Wait longer than the maximum entitlement lifetime plus rollout safety
   margin before marking the prior public key `retired` in a later app release.
6. Remove the prior private key from the server only after that overlap window.

Emergency compromise response:

1. Disable checkout and entitlement signing.
2. Generate a new pair and deploy the new private key.
3. Mark the compromised public key retired, build an emergency desktop update,
   and require online verification after update.
4. Review license state-history and website access logs using IDs only; do not
   collect finance data.
5. Previously installed apps retain risk until their compromised-key envelopes
   expire or they install the emergency build. Record that interval explicitly
   in the incident report.

## Payment reversal state machine

The database recalculates state from the latest event for each provider object,
using provider occurrence time rather than webhook arrival order.

| Payment condition | Purchase status | License status |
|---|---|---|
| Paid, region verified, no adverse event | `paid` | `active` |
| Missing/mismatched amount, currency, account email, pricing version, or regional proof | `pricing_review` | `suspended` |
| Pending or partial refund | `refund_pending` / `partially_refunded` | `suspended` |
| Open dispute | `disputed` | `suspended` |
| Full refund | `refunded` | `revoked` |
| Lost dispute | `dispute_lost` | `revoked` |
| Won/closed dispute or failed refund with no other adverse state | `paid` | `active` |

Every Cashfree event ID is unique. Replays do not duplicate rows or license
changes. Raw webhook bodies are not stored; the event ledger retains bounded
provider IDs, normalized state, amount/currency, occurrence time, and a SHA-256
digest for support reconciliation.

## Regional pricing controls

- The request body contains only the product code. It cannot choose a country.
- When PPP is enabled, Vercel's server-populated country header selects the
  India table only for `IN`; missing or any other signal uses the higher US
  anchor.
- Checkout creates a Cashfree order from the server-side product catalog. The
  browser never supplies an amount, currency, country, or entitlement.
- Fulfillment retrieves the authoritative order and payment from Cashfree and
  rechecks the amount, currency, paid/success state, account email, product,
  user ID, and pricing-table version.
- PPP checkout remains disabled. A future non-India rollout requires an
  authoritative billing-country signal and qualified tax review; Vercel's edge
  country alone is not enough to authorize a regional price.
- A mismatch creates a suspended review record and never emails a usable
  license. Support must resolve or refund it; it must never be manually marked
  active without reviewed billing evidence.

PPP coefficients and tax treatment require qualified annual review. Cashfree's
production KYC, tax/invoice configuration, international-payment approval, and test/live
webhooks are provider release gates.

## Supabase migration and RLS procedure

1. Review the checked-in migration hash and run the source contract verifier.
2. Start a disposable local Supabase stack, run `supabase db reset`,
   `supabase db lint --local --fail-on error`, and `supabase test db` from the
   website directory.
3. Confirm the pgTAP suite covers two-user isolation, role grants, partial/full
   refunds, duplicate and out-of-order events, dispute resolution, revoked
   verification, and the fourth-device rejection.
4. Apply the migration to a non-production Supabase branch/project first.
5. Record the exact migration SHA-256 in `godfin_migration_evidence`; never
   claim a migration is deployed based only on source presence.
6. Repeat two-user authenticated reads and service-role function checks on the
   target project, then capture secret-free evidence.
7. Back up relevant website licensing tables before production migration and
   document the rollback decision. Do not attempt to roll back by deleting
   purchase or event history.

## Provider reconciliation checklist

- Cashfree endpoint subscribes to payment success/failure/user-dropped,
  refund/auto-refund, and dispute created/updated/closed events.
- Sandbox and production credentials remain separate and never enter source control.
- A complete test purchase provisions one lifetime license and sends one email.
- Duplicate delivery leaves one purchase, one provider-event row, and one email.
- A partial refund suspends; a full refund revokes; a won dispute restores only
  when no other adverse condition remains.
- The next online desktop verification rejects a suspended/revoked license and
  removes its cached paid entitlement.
- Three installations verify; a fourth does not. Account deactivation frees a
  slot without deleting history.
- Cashfree invoices/receipts, GST/tax treatment, refund policy, and regional prices receive
  qualified tax/legal review before checkout is enabled.
