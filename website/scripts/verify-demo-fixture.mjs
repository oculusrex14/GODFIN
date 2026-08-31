import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";

const websiteRoot = process.cwd();
const repoRoot = path.resolve(websiteRoot, "..");
const fixture = JSON.parse(
  await readFile(path.join(repoRoot, "backend/tests/fixtures/golden_ledger_v1.json"), "utf8"),
);
const demo = JSON.parse(
  await readFile(path.join(websiteRoot, "public/demo/demo-data.json"), "utf8"),
);

assert.equal(demo.source_schema_version, fixture.schema_version);
assert.equal(demo.disclosure, "Demo data - made-up household - nothing here is connected to a bank");
assert.deepEqual(demo.summary, {
  income: fixture.expected.month.income,
  spend: fixture.expected.month.spend,
  net: fixture.expected.month.net,
  savings_rate: fixture.expected.month.savings_rate,
  balance_status: "unavailable",
  balance_reason: "Two synthetic statement controls conflict, so GODFIN does not guess a balance.",
});
assert.equal(demo.transactions.length, fixture.expected.month.listed_transaction_count);
for (const [index, transaction] of fixture.transactions.filter((row) => row.date.startsWith("2026-07")).entries()) {
  const publicRow = demo.transactions[index];
  assert.equal(publicRow.id, transaction.id);
  assert.equal(publicRow.amount, transaction.amount);
  assert.equal(publicRow.direction, transaction.direction);
}
assert.equal(demo.subscriptions.monthly, fixture.expected.subscriptions.monthly);
assert.equal(demo.subscriptions.annual, fixture.expected.subscriptions.annual);
assert.equal(demo.goal.saved, fixture.expected.goal.balance);
assert.equal(demo.goal.entries.length, fixture.expected.goal.entry_count);
assert.equal(demo.net_worth.assets, fixture.expected.net_worth.assets);
assert.equal(demo.net_worth.liabilities, fixture.expected.net_worth.liabilities);
assert.equal(demo.net_worth.net, fixture.expected.net_worth.net);
assert.equal(demo.financial_year.income, fixture.expected.financial_year.income);
assert.equal(demo.financial_year.spend, fixture.expected.financial_year.spend);

console.log("Public demo snapshot matches the frozen golden-ledger acceptance fixture.");
