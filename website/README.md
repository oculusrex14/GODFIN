# GODFIN website

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

1. Create a Supabase project and run
   `supabase/migrations/0001_website_licensing.sql` in its SQL editor.
2. Enable Google sign-in in Supabase Auth. Configure:
   - Site URL: `https://godfin.dev`
   - Redirect URL: `https://godfin.dev/auth/callback`
3. Create five Stripe **one-time** INR prices matching `src/lib/products.ts`.
   Do not create recurring prices or subscription Checkout sessions.
4. Add a Stripe webhook for
   `https://godfin.dev/api/webhook` with these events:
   - `checkout.session.completed`
   - `checkout.session.async_payment_succeeded`
5. Verify `godfin.dev` in Resend and use a sender such as
   `GODFIN <licenses@godfin.dev>`.
6. Set every `.env.example` value in Vercel. Generate
   `LICENSE_SIGNING_SECRET` with at least 32 random bytes and never rotate it
   without a license migration, because issued keys are deterministically
   derived from it.
7. Build with `npm run build`, deploy the saved private repository to Vercel,
   then complete the release checks in
   [`../docs/PRODUCTION_RELEASE.md`](../docs/PRODUCTION_RELEASE.md).

## Payment and license invariants

- Checkout is always `mode: "payment"`.
- Product codes, INR amounts, and Stripe price IDs are selected server-side.
- Webhooks are verified against the raw body before fulfillment.
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
