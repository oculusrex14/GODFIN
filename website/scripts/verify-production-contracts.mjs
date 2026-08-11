import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
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
assert.match(checkout, /mode:\s*"payment"/);
assert.doesNotMatch(checkout, /mode:\s*"subscription"/);
assert.match(checkout, /stripePriceIdForEnvironment/);
assert.match(checkout, /isRetiredHostedCreditCode/);
assert.match(checkout, /status:\s*410/);

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
assert.match(webhook, /webhooks\.constructEvent/);
assert.match(webhook, /checkout\.session\.completed/);
assert.match(webhook, /checkout\.session\.async_payment_succeeded/);
assert.match(webhook, /session\.amount_total\s*!==\s*expected\.amount/);

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

const envExample = await text(".env.example");
for (const name of [
  "STRIPE_PRICE_PRO_US",
  "STRIPE_PRICE_MAX_US",
  "PPP_CHECKOUT_ENABLED",
  "LICENSE_SIGNING_SECRET",
  "RESEND_API_KEY",
  ...publicClaimsPolicy.required_launch_gates,
]) {
  assert.match(envExample, new RegExp(`^${name}=`, "m"), `${name} is undocumented.`);
}

console.log("Website payment, entitlement, privacy-claim, licensing, and launch-gate contracts pass.");
