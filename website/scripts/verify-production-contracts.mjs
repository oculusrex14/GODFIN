import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";

const websiteRoot = path.resolve(process.cwd());
const repoRoot = path.resolve(websiteRoot, "..");

async function text(relativePath, from = websiteRoot) {
  return readFile(path.join(from, relativePath), "utf8");
}

const shared = JSON.parse(await text("shared/entitlements.json", repoRoot));
const generated = JSON.parse(await text("src/generated/entitlements.json"));
assert.deepEqual(generated, shared, "Website entitlements must match the shared manifest.");
assert.equal(shared.license_model, "lifetime");
assert.equal(shared.included_hosted_ai_credits, 0);
assert.equal(shared.tiers.pro.activation_limit, 3);
assert.equal(shared.tiers.max.activation_limit, 3);
assert.equal(shared.tiers.pro.price.IN.amount_minor, 499900);
assert.equal(shared.tiers.max.price.IN.amount_minor, 999900);
assert.equal(shared.tiers.pro.price.US.amount_minor, 9900);
assert.equal(shared.tiers.max.price.US.amount_minor, 19900);

for (const tier of ["free", "pro", "max"]) {
  for (const feature of shared.tiers[tier].released_features) {
    assert.equal(
      shared.features[feature]?.status,
      "released",
      `${tier} advertises unreleased feature ${feature}`,
    );
  }
}

const products = await text("src/lib/products.ts");
assert.match(products, /pro:[\s\S]*?amount:\s*499900[\s\S]*?credits:\s*0/);
assert.match(products, /max:[\s\S]*?amount:\s*999900[\s\S]*?credits:\s*0/);

const checkout = await text("src/app/api/checkout/route.ts");
assert.match(checkout, /mode:\s*"payment"/);
assert.doesNotMatch(checkout, /mode:\s*"subscription"/);
assert.match(checkout, /stripePriceIdForEnvironment/);

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
]) {
  assert.match(envExample, new RegExp(`^${name}=`, "m"), `${name} is undocumented.`);
}

console.log("Website lifetime-payment, entitlement, PPP, licensing, and waitlist contracts pass.");
