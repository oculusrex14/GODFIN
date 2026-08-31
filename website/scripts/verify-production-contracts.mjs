import assert from "node:assert/strict";
import { readdir, readFile, stat } from "node:fs/promises";
import path from "node:path";
import process from "node:process";

const websiteRoot = path.resolve(process.cwd());
const repoRoot = path.resolve(websiteRoot, "..");

async function text(relativePath, from = websiteRoot) {
  return readFile(path.join(from, relativePath), "utf8");
}

const generated = JSON.parse(await text("src/generated/entitlements.json"));
const generatedPublicClaimsPolicy = JSON.parse(
  await text("src/generated/public-claims-policy.json"),
);
let publicClaimsPolicy = generatedPublicClaimsPolicy;
try {
  const sharedPublicClaimsPolicy = JSON.parse(
    await text("docs/production-remediation/PUBLIC_CLAIMS_POLICY.json", repoRoot),
  );
  assert.deepEqual(
    generatedPublicClaimsPolicy,
    sharedPublicClaimsPolicy,
    "Website public claims policy must match the repository policy.",
  );
  publicClaimsPolicy = sharedPublicClaimsPolicy;
} catch (error) {
  if (error?.code !== "ENOENT") {
    throw error;
  }
}
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
assert.equal(manifest.tiers.free.released_families.length, 12);
assert.equal(manifest.tiers.pro.released_families.length, 15);
assert.equal(manifest.tiers.max.released_families.length, 20);

for (const tier of ["free", "pro", "max"]) {
  const familyFeatures = manifest.tiers[tier].released_families.flatMap(
    (family) => {
      assert.equal(
        manifest.families[family]?.status,
        "released",
        `${tier} advertises unreleased family ${family}`,
      );
      return manifest.families[family].grants;
    },
  );
  assert.deepEqual(
    familyFeatures,
    manifest.tiers[tier].released_features,
    `${tier} feature grants must exactly match its capability families`,
  );
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
  "src/app/demo/page.tsx",
  "src/app/how-it-works/page.tsx",
  "src/app/pricing/page.tsx",
  "src/app/docs/page.tsx",
  "src/app/download/page.tsx",
  "src/app/privacy/page.tsx",
  "src/app/terms/page.tsx",
  "src/app/account/page.tsx",
  "src/components/public-demo.tsx",
  "src/components/product-demo-video.tsx",
  "src/components/site-header.tsx",
  "src/components/site-footer.tsx",
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

const siteHeader = await text("src/components/site-header.tsx");
for (const [href, label] of [
  ["/demo", "Demo"],
  ["/how-it-works", "How it works"],
  ["/pricing", "Pricing"],
  ["/#waitlist", "Join beta"],
]) {
  assert.equal(
    siteHeader.includes(`{ href: "${href}", label: "${label}" }`),
    true,
    `Primary navigation is missing ${label}.`,
  );
}
assert.match(siteHeader, /href="\/account">Sign in/);

const pricingPage = await text("src/app/pricing/page.tsx");
assert.match(pricingPage, /public checkout is closed/i);
assert.match(pricingPage, /₹4,999/);
assert.match(pricingPage, /₹9,999/);
assert.match(pricingPage, /No bundled AI usage/);
assert.doesNotMatch(pricingPage, /PurchaseButton|INR 1|₹1|PPP|purchasing power/i);

const waitlistForm = await text("src/components/waitlist-form.tsx");
assert.doesNotMatch(
  waitlistForm,
  /name=["']country["']|htmlFor=["']country["']/i,
  "Public waitlist must not require a visible country field.",
);
const waitlistRouteSource = await text("src/app/api/waitlist/route.ts");
const betaLibrary = await text("src/lib/beta.ts");
assert.match(betaLibrary, /x-vercel-ip-country/);
assert.match(waitlistRouteSource, /inferredCountry\(/);
assert.match(waitlistRouteSource, /country_source:\s*countrySource/);

const publicDemo = await text("src/components/public-demo.tsx");
assert.match(publicDemo, /demo-data\.json/);
assert.match(publicDemo, /data-demo-runtime="static"/);
assert.match(publicDemo, /Start 2-minute tour/);
assert.match(publicDemo, /Explore freely/);
assert.match(publicDemo, /ArrowRight/);
assert.match(publicDemo, /ArrowLeft/);
assert.match(publicDemo, /Escape/);
assert.doesNotMatch(publicDemo, /fetch\(|XMLHttpRequest|FormData|type=["']file["']/);
assert.doesNotMatch(publicDemo, /\/api\/|supabase|cashfree|accounts\.google/i);

const demoFixture = JSON.parse(await text("public/demo/demo-data.json"));
assert.equal(
  demoFixture.disclosure,
  "Demo data - made-up household - nothing here is connected to a bank",
);
assert.equal(demoFixture.summary.income, "44000.00");
assert.equal(demoFixture.summary.spend, "11000.00");
assert.equal(demoFixture.summary.net, "33000.00");
assert.equal(demoFixture.transactions.length, 13);

const productDemoVideo = await text("src/components/product-demo-video.tsx");
assert.match(productDemoVideo, /prefers-reduced-motion: reduce/);
assert.match(productDemoVideo, /IntersectionObserver/);
assert.match(productDemoVideo, /poster="\/video\/godfin-beta-hero\.poster\.webp"/);
assert.match(productDemoVideo, /godfin-beta-hero\.webm/);
assert.match(productDemoVideo, /godfin-beta-hero\.mp4/);
assert.match(productDemoVideo, /kind="captions"/);
assert.match(productDemoVideo, /Read the 24-second video transcript/);
assert.match(productDemoVideo, /controls/);
assert.match(productDemoVideo, /muted/);
assert.match(productDemoVideo, /playsInline/);

for (const mediaPath of [
  "public/video/godfin-beta-hero.mp4",
  "public/video/godfin-beta-hero.webm",
  "public/video/godfin-beta-hero.poster.webp",
  "public/video/godfin-beta-hero.en.vtt",
  "public/video/godfin-demo-walkthrough.mp4",
  "public/video/godfin-demo-walkthrough.webm",
  "public/video/godfin-demo-walkthrough.poster.webp",
  "public/video/godfin-beta-social.mp4",
  "public/video/render-verification.json",
]) {
  assert.ok((await stat(path.join(websiteRoot, mediaPath))).size > 0, `${mediaPath} is empty.`);
}

const remotionPackage = JSON.parse(await text("remotion/package.json"));
const websiteTypeScriptConfig = JSON.parse(await text("tsconfig.json"));
assert.ok(
  websiteTypeScriptConfig.exclude?.includes("remotion"),
  "Next.js must not typecheck the isolated Remotion package; Remotion has its own CI gate.",
);
for (const packageName of ["remotion", "@remotion/cli", "@remotion/renderer", "@remotion/bundler"]) {
  assert.equal(
    remotionPackage.dependencies?.[packageName],
    "4.0.518",
    `${packageName} must remain exactly pinned for deterministic rendering.`,
  );
}
const remotionRoot = await text("remotion/src/root.tsx");
for (const composition of [
  ["GodfinBetaHero16x9", 1920, 1080, 720],
  ["GodfinDemoWalkthrough16x9", 1920, 1080, 1620],
  ["GodfinBetaSocial9x16", 1080, 1920, 540],
]) {
  const [id, width, height, duration] = composition;
  assert.match(
    remotionRoot,
    new RegExp(
      `id: \\"${id}\\", width: ${width}, height: ${height}, fps: 30, durationInFrames: ${duration}`,
    ),
  );
}
assert.doesNotMatch(
  await text("src/app/page.tsx"),
  /godfin-workflow\.(mp4|webm)/,
  "The public page must not reuse the mixed-fixture legacy workflow capture.",
);

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

const betaCheckoutRoute = await text("src/app/api/beta/checkout/route.ts");
for (const requiredContract of [
  /betaCheckoutConfigured\(\)/,
  /tester\?\.checkoutEligible/,
  /godfin_beta_/,
  /BETA_CHECKOUT_AMOUNT_MINOR/,
  /BETA_CHECKOUT_CURRENCY/,
  /BETA_CHECKOUT_PRODUCT_CODE/,
  /BETA_CHECKOUT_FLOW/,
  /onConflict:\s*"provider_order_id",\s*ignoreDuplicates:\s*true/,
  /attempt\.beta_tester_id !== tester\.id/,
  /attempt\.user_id !== user\.id/,
]) {
  assert.match(betaCheckoutRoute, requiredContract);
}
assert.match(envModule, /BETA_CHECKOUT_ENABLED/);
assert.match(envModule, /BETA_CHECKOUT_LIVE_ENABLED/);
assert.match(envModule, /CASHFREE_ENVIRONMENT[\s\S]*?!== "production"/);
assert.match(envModule, /productionAllowed/);

const downloadPage = await text("src/app/download/page.tsx");
assert.match(downloadPage, /BETA_MAC_APPLE_SILICON_DOWNLOAD_URL/);
assert.match(downloadPage, /BETA_WINDOWS_X64_DOWNLOAD_URL/);
assert.match(downloadPage, /robots:\s*\{\s*index:\s*false/);
assert.doesNotMatch(downloadPage, /NEXT_PUBLIC_.*DOWNLOAD_URL/);

for (const scopedCookieRoute of [
  "src/app/api/beta/invite/claim/route.ts",
  "src/app/api/beta/invite/accept/route.ts",
]) {
  assert.match(await text(scopedCookieRoute), /path:\s*"\/api\/beta\/invite"/);
}
for (const scopedCookieRoute of [
  "src/app/api/waitlist/confirm/route.ts",
  "src/app/api/waitlist/profile/route.ts",
]) {
  assert.match(await text(scopedCookieRoute), /path:\s*"\/api\/waitlist\/profile"/);
}

const betaMigration = await text(
  "supabase/migrations/20260830044445_beta_waitlist_access_entitlements_feedback.sql",
);
for (const requiredSql of [
  /create table if not exists public\.beta_candidate_profiles/,
  /create table if not exists public\.beta_testers/,
  /create table if not exists public\.beta_invites/,
  /create table if not exists public\.beta_feedback/,
  /create table if not exists public\.beta_checkout_attempts/,
  /create table if not exists public\.beta_events/,
  /event_key text unique/,
  /create or replace function public\.accept_beta_invite/,
  /create or replace function public\.set_beta_tester_access/,
  /create or replace function public\.verify_license/,
  /kind in \('purchase', 'owner_test', 'beta_test'\)/,
  /v_license\.kind = 'beta_test'/,
  /v_license\.expires_at <= now\(\)/,
  /grant execute on function public\.accept_beta_invite[\s\S]*?to service_role/,
  /grant execute on function public\.set_beta_tester_access[\s\S]*?to service_role/,
  /grant execute on function public\.verify_license[\s\S]*?to service_role/,
]) {
  assert.match(betaMigration, requiredSql);
}
for (const betaTable of [
  "beta_candidate_profiles",
  "beta_testers",
  "beta_invites",
  "beta_feedback",
  "beta_checkout_attempts",
  "beta_events",
]) {
  assert.match(betaMigration, new RegExp(`alter table public\\.${betaTable} enable row level security`));
}

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
assert.match(webhook, /readCappedWebhookBody/);
assert.match(webhook, /checkRateLimit/);
assert.match(webhook, /limit: 600/);
assert.match(webhook, /email_claimed_at/);
assert.match(webhook, /maybeSingle/);
assert.match(webhook, /errorType/);
assert.doesNotMatch(webhook, /error instanceof Error \? error\.message/);

const cashfree = await text("src/lib/cashfree.ts");
assert.match(cashfree, /CASHFREE_API_VERSION = "2025-01-01"/);
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

const cashfreeUpgradeMigration = await text(
  "supabase/migrations/0007_cashfree_license_upgrades.sql",
);
for (const requiredSql of [
  /purchase_kind text not null default 'base'/,
  /product_code = 'pro_to_max'/,
  /create unique index if not exists purchases_one_base_per_license_idx/,
  /create or replace function private\.cashfree_purchase_state/,
  /v_has_paid_upgrade/,
  /v_desired_tier := case/,
  /state_version = state_version \+ 1/,
  /p_purchase_kind text/,
  /p_upgrade_license_id uuid/,
  /A purchase license already exists for this account/,
  /grant execute on function public\.provision_cashfree_purchase[\s\S]*?to service_role/,
]) {
  assert.match(cashfreeUpgradeMigration, requiredSql);
}
assert.match(checkout, /resolveLicenseCheckout/);
assert.match(checkout, /isPublicLicenseProduct/);
assert.match(await text("src/lib/products.ts"), /pro_to_max/);

const middleware = await text("src/middleware.ts");
const nextConfig = await text("next.config.ts");
const rootLayout = await text("src/app/layout.tsx");
assert.match(middleware, /crypto\.randomUUID\(\)/);
assert.match(middleware, /'nonce-\$\{nonce\}' 'strict-dynamic'/);
assert.match(middleware, /style-src-elem 'self' 'nonce-\$\{nonce\}'/);
assert.match(
  middleware,
  /style-src-attr 'unsafe-hashes' 'sha256-zlqnbDt84zf1iSefLU\/ImC54isoprH\/MRiVZGskwexk='/,
);
assert.match(
  middleware,
  /if \(upgradeInsecureRequests\) directives\.push\("upgrade-insecure-requests"\)/,
);
assert.match(middleware, /forwardedProtocol === "https"/);
assert.match(middleware, /request\.nextUrl\.protocol === "https:"/);
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

const generatedPublicKeyManifest = JSON.parse(
  await text("src/generated/license-entitlement-public-keys.json"),
);
let publicKeyManifest = generatedPublicKeyManifest;
try {
  const sharedPublicKeyManifest = JSON.parse(
    await text("shared/license-entitlement-public-keys.json", repoRoot),
  );
  assert.deepEqual(
    generatedPublicKeyManifest,
    sharedPublicKeyManifest,
    "Website license public keys must match the shared manifest.",
  );
  publicKeyManifest = sharedPublicKeyManifest;
} catch (error) {
  if (error?.code !== "ENOENT") {
    throw error;
  }
}
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
  "BETA_MAC_APPLE_SILICON_DOWNLOAD_URL",
  "BETA_WINDOWS_X64_DOWNLOAD_URL",
  "BETA_CHECKOUT_ENABLED",
  "BETA_CHECKOUT_LIVE_ENABLED",
  ...publicClaimsPolicy.required_launch_gates,
]) {
  assert.match(envExample, new RegExp(`^${name}=`, "m"), `${name} is undocumented.`);
}

console.log("Website payment, entitlement, privacy-claim, licensing, and launch-gate contracts pass.");
