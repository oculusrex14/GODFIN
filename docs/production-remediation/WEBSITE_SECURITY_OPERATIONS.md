# Website Security Operations

This runbook covers the repository-level controls for `GF-WEB-001`. It contains no production secret values.

## Public endpoint abuse controls

GODFIN applies a durable fixed-window limiter before public or provider-costing work. Counters are stored in Supabase by `public.check_public_rate_limit`; the function performs one atomic upsert and is executable only by `service_role`. Neither anonymous nor authenticated browser roles can read the counter table or invoke the function.

The limiter never stores a raw IP address, email address, user ID, or license key. The server derives a purpose-specific HMAC-SHA256 subject using `ABUSE_HASH_SECRET`. Production requests use Vercel's overwritten forwarding address header. A missing or malformed address is deliberately grouped into one conservative `unavailable` subject.

| Operation | Subject | Limit |
| --- | --- | ---: |
| Waitlist submission | Network address | 5/hour |
| Waitlist submission | Normalized email | 3/day |
| Waitlist confirmation | Network address | 30/hour |
| License email resend | Network address | 15/day |
| License email resend | Signed-in user | 3/day |
| License verification | Network address | 120/hour |
| License verification | License-key hash | 30/hour |
| Checkout creation | Network address | 20/hour |
| Checkout creation | Signed-in user | 10/hour |
| OAuth callback | Network address | 60/hour |

Blocked JSON responses use HTTP 429, `Retry-After`, `Cache-Control: no-store`, and remaining-limit headers. Failures in the durable control fail closed before email, Cashfree, licensing, or OAuth work. The Cashfree webhook is not application-rate-limited because it already requires Cashfree's signed raw-body payload and must remain retryable; provider ingress controls should protect it without rejecting legitimate retries.

### Secret setup and rotation

Generate `ABUSE_HASH_SECRET` with at least 32 random bytes and set it only in the Vercel production/preview environment. Never expose it with a `NEXT_PUBLIC_` prefix. Rotating the value intentionally creates new pseudonymous subjects; existing counter rows then expire naturally. Rotate immediately if the value may have been exposed.

The deployment must not enable checkout or waitlist submission until the secret and migration `0005_public_abuse_controls.sql` are present. After applying the migration, run the Supabase pgTAP suite and verify that anonymous/authenticated roles cannot access the table or function.

## Content Security Policy

Every HTML request receives a cryptographically random nonce through Next.js middleware. The nonce is placed on framework, Cashfree checkout, and privacy-analytics scripts. Production policy uses `strict-dynamic`, has no `unsafe-inline` or `unsafe-eval`, blocks inline style attributes and object embedding, disallows framing, and permits only the explicitly listed Supabase, Cashfree, Google sign-in, and privacy-analytics connections. Arbitrary WebSocket origins are permitted only by the development policy.

API responses receive a separate `default-src 'none'` policy and `Cache-Control: no-store`. The nonce policy requires dynamic rendering of HTML routes; performance must be measured against the website budget before launch.

Next Image currently emits harmless `style="color:transparent"` attributes for image placeholders. The policy blocks those attributes. Browser acceptance testing must confirm that real images, focus states, checkout, Google sign-in, and reduced-motion fallbacks remain usable and that the production console contains no unexpected CSP violations.

## Repository verification

Run from `website/`:

```sh
npm run verify:contracts
npm run lint
npm run build
```

The contract verifier enforces rate-limit coverage, privileged SQL grants, CSP nonces, the absence of `unsafe-inline`, and the absence of React inline-style objects. The ordered migration manifest protects all Supabase migration bytes.

Repository verification is not a substitute for the deferred provider/browser checks: run the pgTAP suite against a disposable Supabase database, configure external edge/WAF limits, inspect live response headers, and complete browser accessibility and functional flows before public launch.
