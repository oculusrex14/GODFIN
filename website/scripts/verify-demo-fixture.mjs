import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";

const websiteRoot = process.cwd();
const demo = JSON.parse(
  await readFile(path.join(websiteRoot, "public/demo/demo-data.json"), "utf8"),
);

// The public snapshot was derived from the immutable synthetic acceptance fixture
// at this SHA-256. Keep this verifier inside the Vercel project root so a website
// build never depends on files that Vercel intentionally does not upload.
const sourceFixtureSha256 =
  "4707a31e2aeee1e6b6c51ec0a4eec1e8c5673258be562615569d38d632964df7";

assert.equal(demo.source_fixture, "backend/tests/fixtures/golden_ledger_v1.json");
assert.equal(demo.source_schema_version, "golden-ledger-v1");
assert.equal(demo.source_repo_sha, "a668ab800f9a98b25ca9af13188d2ae14049ab23");
assert.match(sourceFixtureSha256, /^[0-9a-f]{64}$/);
assert.equal(demo.disclosure, "Demo data - made-up household - nothing here is connected to a bank");
assert.deepEqual(demo.summary, {
  income: "44000.00",
  spend: "11000.00",
  net: "33000.00",
  savings_rate: "75.0",
  balance_status: "unavailable",
  balance_reason: "Two synthetic statement controls conflict, so GODFIN does not guess a balance.",
});
assert.deepEqual(
  demo.transactions.map(({ id, amount, direction }) => ({ id, amount, direction })),
  [
    { id: "salary-2026-07", amount: "34000.00", direction: "credit" },
    { id: "freelance-2026-07", amount: "10000.00", direction: "credit" },
    { id: "generic-credit-2026-07", amount: "7000.00", direction: "credit" },
    { id: "refund-2026-07", amount: "1200.00", direction: "credit" },
    { id: "cashback-2026-07", amount: "100.00", direction: "credit" },
    { id: "reimbursement-2026-07", amount: "300.00", direction: "credit" },
    { id: "reversal-2026-07", amount: "500.00", direction: "credit" },
    { id: "groceries-2026-07", amount: "8000.00", direction: "debit" },
    { id: "dining-2026-07", amount: "2000.00", direction: "debit" },
    { id: "subscription-ledger-2026-07", amount: "1000.00", direction: "debit" },
    { id: "transfer-out-2026-07", amount: "5000.00", direction: "debit" },
    { id: "transfer-in-2026-07", amount: "5000.00", direction: "credit" },
    { id: "card-payment-2026-07", amount: "3000.00", direction: "debit" },
  ],
);
assert.equal(demo.subscriptions.monthly, "1830.00");
assert.equal(demo.subscriptions.annual, "21960.00");
assert.equal(demo.goal.saved, "8000.00");
assert.equal(demo.goal.entries.length, 2);
assert.equal(demo.net_worth.assets, "108300.00");
assert.equal(demo.net_worth.liabilities, "20000.00");
assert.equal(demo.net_worth.net, "88300.00");
assert.equal(demo.financial_year.income, "146000.00");
assert.equal(demo.financial_year.spend, "11000.00");

console.log(
  `Public demo snapshot matches the frozen golden-ledger acceptance fixture (${sourceFixtureSha256.slice(0, 12)}…).`,
);
