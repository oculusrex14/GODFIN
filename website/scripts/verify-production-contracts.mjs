import assert from "node:assert/strict";
import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";

const websiteRoot = path.resolve(process.cwd());
const repoRoot = path.resolve(websiteRoot, "..");

async function text(relativePath, from = websiteRoot) {
  return readFile(path.join(from, relativePath), "utf8");
}

const generated = JSON.parse(await text("src/generated/entitlements.json"));
const publicClaimsPolicy = JSON.parse(
  await text("docs/production-remediation/PUBLIC_CLAIMS_POLICY.json", repoRoot),
);
let manifest = generated;
try {
  const shared = JSON.parse(await text("shared/entitlements.json", repoRoot));
  assert.deepEqual(
    generated,
    shared,
    "Website entitlements must match the shared manifest.",
  );
  manifest = shared;
} catch (error) {
  if (error?.code !== "ENOENT") {
    throw error;
  }
}

assert.equal(manifest.license_model, "lifetime");
assert.equal(manifest.included_hosted_ai_credits, 0);
assert.equal(manifest.tiers.pro.activation_limit, 3);
assert.equal(manifest.tiers.max.activation_limit, 3);
assert.equal(manifest.tiers.pro.price.IN.amount_minor, 499900);
assert.equal(manifest.tiers.max.price.IN.amount_minor, 999900);
assert.equal(manifest.tiers.pro.price.US.amount_minor, 9900);
assert.equal(manifest.tiers.max.price.US.amount_minor, 19900);

for (const tier of ["free", "pro", "max"]) {
  for (const feature of manifest.tiers[tier].released_features) {
    assert.equal(
      manifest.features[feature]?.status,
      "released",
      `${tier} advertises unreleased feature ${feature}`,
    );
  }
}

const products = await text("src/lib/products.ts");
assert.match(products, /pro:[\s\S]*?amount:\s*499900[\s\S]*?credits:\s*0/);
assert.match(products, /max:[\s\S]*?amount:\s*999900[\s\S]*?credits:\s*0/);
assert.doesNotMatch(products, /credits_(starter|regular|power)\s*:/);
assert.match(products, /isRetiredHostedCreditCode/);

const checkout = await text("src/app/api/checkout/route.ts");
assert.match(checkout, /createCashfreeOrder/);
assert.match(checkout, /paymentSessionId/);
assert.match(checkout, /checkoutAttemptId/);
assert.doesNotMatch(checkout, /Stripe|stripePriceIdForEnvironment/);
assert.match(checkout, /isRetiredHostedCreditCode/);
assert.match(checkout, /status:\s*410/);
assert.match(checkout, /requestPricingCountry\(request\)/);
assert.doesNotMatch(checkout, /body\.country/);

const purchaseButton = await text("src/components/purchase-button.tsx");
assert.match(purchaseButton, /checkoutAttemptId:\s*checkoutAttemptId\.current/);
assert.match(purchaseButton, /cashfree\.checkout/);
assert.match(purchaseButton, /document\.createElement\("script"\)/);
assert.match(purchaseButton, /https:\/\/sdk\.cashfree\.com\/js\/v3\/cashfree\.js/);
assert.doesNotMatch(purchaseButton, /checkoutCountry|localeCountry/);

const regionalPricing = await text("src/lib/regional-pricing.ts");
assert.match(regionalPricing, /x-vercel-ip-country/);
assert.match(regionalPricing, /country === "IN" \? "IN" : "US"/);

const abuseControl = await text("src/lib/abuse-control.ts");
assert.match(abuseControl, /x-vercel-forwarded-for/);
assert.match(abuseControl, /createHmac\("sha256", serverEnv\.abuseHashSecret\(\)\)/);
assert.match(abuseControl, /check_public_rate_limit/);
assert.match(abuseControl, /status:\s*429/);
for (const rateLimitedRoute of [
  "src/app/api/checkout/route.ts",
  "src/app/api/waitlist/route.ts",
  "src/app/api/waitlist/confirm/route.ts",
  "src/app/api/license/resend/route.ts",
  "src/app/api/license/verify/route.ts",
  "src/app/auth/callback/route.ts",
]) {
  assert.match(
    await text(rateLimitedRoute),
    /checkRateLimit/,
    `${rateLimitedRoute} is missing durable abuse control.`,
  );
}

const publicContentPaths = [
  "src/app/page.tsx",
  "src/app/pricing/page.tsx",
  "src/app/docs/page.tsx",
  "src/app/download/page.tsx",
  "src/app/privacy/page.tsx",
  "src/app/terms/page.tsx",
  "src/app/account/page.tsx",
  "src/components/privacy-analytics.tsx",
];
const publicContent = [];
for (const publicPage of publicContentPaths) {
  const page = await text(publicPage);
  publicContent.push(page);
  assert.doesNotMatch(
    page,
    /Buy (Starter|Regular|Power)|Purchased top-ups|AI top-up balance/i,
    `${publicPage} must not market or display unusable hosted-credit products.`,
  );
}

const joinedPublicContent = publicContent.join("\n").toLowerCase();
for (const phrase of publicClaimsPolicy.prohibited_public_phrases) {
  assert.equal(
    joinedPublicContent.includes(phrase.toLowerCase()),
    false,
    `Public content contains prohibited claim or placeholder: ${phrase}`,
  );
}

const privacyPage = await text("src/app/privacy/page.tsx");
const normalizedPrivacyPage = privacyPage.replace(/\s+/g, " ").toLowerCase();
for (const disclosure of publicClaimsPolicy.required_privacy_disclosures) {
  assert.equal(
    normalizedPrivacyPage.includes(disclosure.toLowerCase()),
    true,
    `Privacy policy is missing required disclosure: ${disclosure}`,
  );
}

const envModule = await text("src/lib/env.ts");
assert.match(envModule, /commerceConfigured/);
assert.match(envModule, /waitlistConfigured/);
assert.match(checkout, /commerceConfigured\(\)/);
const waitlistRoute = await text("src/app/api/waitlist/route.ts");
assert.match(waitlistRoute, /waitlistConfigured\(\)/);

const webhook = await text("src/app/api/webhook/route.ts");
assert.match(webhook, /verifyCashfreeWebhook/);
assert.match(webhook, /getCashfreeOrder/);
assert.match(webhook, /getCashfreePayments/);
for (const eventType of [
  "PAYMENT_SUCCESS_WEBHOOK",
  "PAYMENT_FAILED_WEBHOOK",
  "PAYMENT_USER_DROPPED_WEBHOOK",
  "REFUND_STATUS_WEBHOOK",
  "AUTO_REFUND_STATUS_WEBHOOK",
  "DISPUTE_CREATED",
  "DISPUTE_UPDATED",
  "DISPUTE_CLOSED",
]) {
  assert.equal(
    webhook.includes(`"${eventType}"`),
    true,
    `Webhook is missing ${eventType}.`,
  );
}
assert.match(webhook, /record_cashfree_payment_event/);
assert.match(webhook, /createHash\("sha256"\)\.update\(rawBody\)/);
assert.match(webhook, /order_amount_mismatch/);
assert.match(webhook, /payment_amount_mismatch/);
assert.match(webhook, /account_email_mismatch/);
assert.match(webhook, /billing_country_unverified/);
assert.match(webhook, /provisioned\?\.license_status === "active"/);

const cashfree = await text("src/lib/cashfree.ts");
assert.match(cashfree, /CASHFREE_API_VERSION = "2026-01-01"/);
assert.match(cashfree, /"x-idempotency-key"/);
assert.match(cashfree, /timestamp \+ rawBody/);
assert.match(cashfree, /createHmac\("sha256", serverEnv\.cashfreeClientSecret\(\)\)/);
assert.match(cashfree, /timingSafeEqual/);
assert.match(cashfree, /WEBHOOK_CLOCK_SKEW_MS = 5 \* 60 \* 1000/);

const migration = await text("supabase/migrations/0002_phase2_entitlements_waitlist.sql");
assert.match(migration, /p_activation_limit integer/);
assert.match(migration, /v_activation_count >= p_activation_limit/);
assert.match(migration, /deactivated_at is null/);
assert.match(migration, /waitlist_entries/);

const ownerLicenseMigration = await text(
  "supabase/migrations/0003_owner_test_licenses.sql",
);
assert.match(ownerLicenseMigration, /kind in \('purchase', 'owner_test'\)/);
assert.match(ownerLicenseMigration, /where kind = 'owner_test' and status = 'active'/);
assert.doesNotMatch(ownerLicenseMigration, /insert into public\.purchases/i);

const hardenedMigration = await text(
  "supabase/migrations/0004_signed_entitlements_payment_reversals_rls.sql",
);
for (const requiredSql of [
  /create table if not exists public\.payment_events/,
  /create table if not exists public\.license_status_history/,
  /create or replace function private\.recompute_purchase_license_state/,
  /create or replace function public\.record_payment_event/,
  /create or replace function public\.verify_license/,
  /set search_path = ''/,
  /grant execute on function public\.record_payment_event[\s\S]*?to service_role/,
  /v_refund_total > 0 and v_refund_total >= v_purchase\.amount_total/,
  /v_previous_status/,
  /state_version = state_version \+ 1/,
  /p_activation_limit > 3/,
]) {
  assert.match(hardenedMigration, requiredSql);
}
const privilegedFunctionGrants = [
  ...hardenedMigration.matchAll(
    /grant execute on function public\.(provision_purchase|record_payment_event|verify_license)\([\s\S]*?\)\s+to\s+([^;]+);/g,
  ),
];
assert.equal(privilegedFunctionGrants.length, 3);
for (const grant of privilegedFunctionGrants) {
  assert.equal(grant[2].trim(), "service_role");
}

const abuseMigration = await text(
  "supabase/migrations/0005_public_abuse_controls.sql",
);
for (const requiredSql of [
  /create table if not exists public\.public_rate_limits/,
  /alter table public\.public_rate_limits enable row level security/,
  /create or replace function public\.check_public_rate_limit/,
  /security definer[\s\S]*?set search_path = ''/,
  /on conflict \(bucket, subject_hash\) do update/,
  /grant execute on function public\.check_public_rate_limit[\s\S]*?to service_role/,
]) {
  assert.match(abuseMigration, requiredSql);
}

const cashfreeMigration = await text(
  "supabase/migrations/0006_cashfree_commerce.sql",
);
for (const requiredSql of [
  /payment_provider text not null default 'stripe'/,
  /create or replace function public\.provision_cashfree_purchase/,
  /create or replace function public\.record_cashfree_payment_event/,
  /create or replace function private\.recompute_cashfree_purchase_license_state/,
  /e\.provider_payment_id = p_cf_payment_id/,
  /event_status ~ '_MERCHANT_\(LOST\|ACCEPTED\)\$'/,
  /grant execute on function public\.provision_cashfree_purchase[\s\S]*?to service_role/,
  /grant execute on function public\.record_cashfree_payment_event[\s\S]*?to service_role/,
]) {
  assert.match(cashfreeMigration, requiredSql);
}
assert.doesNotMatch(
  cashfreeMigration,
  /e\.provider_order_id = p_order_id\s*\)\s*;\s*v_license_status/,
  "Cashfree refunds must not map to a purchase by order ID alone.",
);

const middleware = await text("src/middleware.ts");
const nextConfig = await text("next.config.ts");
const rootLayout = await text("src/app/layout.tsx");
assert.match(middleware, /crypto\.randomUUID\(\)/);
assert.match(middleware, /'nonce-\$\{nonce\}' 'strict-dynamic'/);
assert.match(middleware, /style-src-elem 'self' 'nonce-\$\{nonce\}'/);
assert.match(middleware, /style-src-attr 'none'/);
assert.match(
  middleware,
  /connect-src 'self'\$\{development \? " ws: wss:" : ""\}/,
);
assert.doesNotMatch(middleware, /unsafe-inline/);
assert.doesNotMatch(nextConfig, /unsafe-inline/);
assert.match(nextConfig, /default-src 'none'/);
assert.match(rootLayout, /dynamic = "force-dynamic"/);
assert.match(rootLayout, /<PrivacyAnalytics nonce=\{nonce\}/);
assert.doesNotMatch(
  rootLayout,
  /sdk\.cashfree\.com/,
  "Cashfree must load only after the shopper starts checkout.",
);

async function sourceFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const nested = await Promise.all(
    entries.map((entry) => {
      const fullPath = path.join(directory, entry.name);
      return entry.isDirectory() ? sourceFiles(fullPath) : [fullPath];
    }),
  );
  return nested.flat();
}
for (const sourcePath of await sourceFiles(path.join(websiteRoot, "src"))) {
  if (!sourcePath.endsWith(".tsx")) continue;
  assert.doesNotMatch(
    await readFile(sourcePath, "utf8"),
    /style=\{\{/,
    `${path.relative(websiteRoot, sourcePath)} contains an inline style.`,
  );
}

const entitlementSigner = await text("src/lib/entitlement-signing.ts");
assert.match(entitlementSigner, /algorithm:\s*"Ed25519"/);
assert.match(entitlementSigner, /installation_hash:\s*installationHash/);
assert.match(entitlementSigner, /license_state_version:\s*licenseStateVersion/);
assert.match(entitlementSigner, /MAX_TTL_HOURS = 31 \* 24/);
const licenseVerify = await text("src/app/api/license/verify/route.ts");
assert.match(licenseVerify, /signEntitlement/);
assert.match(licenseVerify, /rawResult\.license_id/);
assert.match(licenseVerify, /rawResult\.license_state_version/);

const publicKeyManifest = JSON.parse(
  await text("shared/license-entitlement-public-keys.json", repoRoot),
);
assert.equal(publicKeyManifest.schema_version, 1);
assert.ok(Object.keys(publicKeyManifest.keys).length >= 1);
for (const key of Object.values(publicKeyManifest.keys)) {
  assert.equal(key.algorithm, "Ed25519");
  assert.match(key.public_key_spki_b64, /^[A-Za-z0-9+/]+={0,2}$/);
  assert.equal("private_key" in key, false);
}

const envExample = await text(".env.example");
for (const name of [
  "CASHFREE_CLIENT_ID",
  "CASHFREE_CLIENT_SECRET",
  "CASHFREE_ENVIRONMENT",
  "CASHFREE_GLOBAL_PAYMENTS_APPROVED",
  "PPP_CHECKOUT_ENABLED",
  "LICENSE_SIGNING_SECRET",
  "ABUSE_HASH_SECRET",
  "LICENSE_ENTITLEMENT_ACTIVE_KEY_VERSION",
  "LICENSE_ENTITLEMENT_PRIVATE_KEYS_JSON",
  "RESEND_API_KEY",
  ...publicClaimsPolicy.required_launch_gates,
]) {
  assert.match(envExample, new RegExp(`^${name}=`, "m"), `${name} is undocumented.`);
}

console.log("Website payment, entitlement, privacy-claim, licensing, and launch-gate contracts pass.");
