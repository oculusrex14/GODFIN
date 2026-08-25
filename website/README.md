# GODFIN website

Read [`../docs/ENGINEERING_GUIDE.md`](../docs/ENGINEERING_GUIDE.md) for the
authoritative app/website data boundary and shared release policy.

The public storefront is a Next.js 15 application. It owns marketing,
authentication, one-time payments, license provisioning, and optional AI
credit balances. It must never receive or store the desktop app's statements,
transactions, budgets, merchant memory, PIN, or local SQLite database.

## Local development

```bash
npm ci
cp .env.example .env.local
npm run dev
```

The site runs at `http://localhost:5300`. Static pages and the unconfigured
account state work without credentials. Checkout, Google sign-in, email, and
license verification require the environment variables in `.env.example`.

## Production services

1. Create a dedicated Supabase project and apply every ordered migration under
   `supabase/migrations/` through the Supabase CLI. Do not cherry-pick only the
   first migration.
2. Enable Google sign-in in Supabase Auth with a dedicated website OAuth client.
   Configure the canonical and fallback callbacks:
   - Site URL: `https://godfin.dev`
   - Redirect URL: `https://godfin.dev/auth/callback`
   - Fallback: `https://godfin.vercel.app/auth/callback`
3. Create a Cashfree Payment Gateway app. Keep `CASHFREE_ENVIRONMENT=sandbox`
   and `CHECKOUT_ENABLED=false` until the complete payment test matrix passes.
   GODFIN creates one-time orders from its server-side product catalog; it does
   not create subscriptions.
4. Add the Cashfree webhook `https://godfin.dev/api/webhook` and subscribe to
   payment success/failure/user-dropped, refund/auto-refund, and dispute events.
   The route verifies Cashfree's raw-body HMAC signature and re-fetches paid
   orders server-to-server before it issues a license.
5. Verify the final mail domain in Resend before using an `@godfin.dev` sender.
   The Vercel hostname is a website fallback, not an email domain.
6. Set every `.env.example` value in Vercel. Generate
   licensing key material with the documented rotation procedure. Never commit
   provider secrets or treat a symmetric derivation secret as a signed license
   envelope.
7. Build with `npm run build`, deploy the saved private repository to Vercel,
   then complete the release checks in
   [`../docs/PRODUCTION_RELEASE.md`](../docs/PRODUCTION_RELEASE.md).

## Payment and license invariants

- Checkout always creates one Cashfree order for one lifetime license.
- Product codes, currencies, and amounts are selected server-side.
- Webhooks are verified against the raw body before fulfillment.
- Browser return URLs never activate a license on their own.
- Purchase provisioning is transactional and idempotent in Postgres.
- Full license keys are never stored. Supabase stores only SHA-256 hashes and
  the final four characters.
- The full key is derived only when sending it or showing it to its signed-in
  owner immediately after a paid Checkout session.
- Desktop verification sends only the key, anonymous installation ID, and app
  version.

## Validation

```bash
npm run build
npm audit --omit=dev
```

Repository support does not prove deployed Google OAuth, Cashfree KYC/webhooks,
webhooks, Resend/DNS, RLS, or production environment values. Record those live
checks in the private owner runbook.
