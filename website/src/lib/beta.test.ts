import assert from "node:assert/strict";
import test from "node:test";

import {
  betaCheckoutEligibility,
  betaLicenseKeyForTester,
  cleanText,
  containsSensitiveFeedback,
  inferredCountry,
  normalizeEmail,
  safeAuthNext,
} from "@/lib/beta";

test("normalizes public waitlist identity without inventing a country", () => {
  assert.equal(normalizeEmail(" Person@Example.COM "), "person@example.com");
  assert.equal(normalizeEmail("not-an-email"), null);
  const unknown = inferredCountry(new Request("https://godfin.dev"), "");
  assert.deepEqual(unknown, { country: null, source: "unknown" });
  const edge = inferredCountry(
    new Request("https://godfin.dev", {
      headers: { "x-vercel-ip-country": "in" },
    }),
    "US",
  );
  assert.deepEqual(edge, { country: "IN", source: "vercel_geo" });
});

test("auth continuations are exact same-origin destinations", () => {
  assert.equal(safeAuthNext("/beta"), "/beta");
  assert.equal(safeAuthNext("/download"), "/download");
  assert.equal(safeAuthNext("//evil.example"), "/account");
  assert.equal(safeAuthNext("/beta?next=https://evil.example"), "/account");
  assert.equal(safeAuthNext("https://evil.example"), "/account");
});

test("beta license derivation is stable and independent from the promoted tier", () => {
  const key = betaLicenseKeyForTester(
    "11111111-1111-4111-8111-111111111111",
    "a-secret-longer-than-twenty-four-characters",
  );
  assert.match(key, /^GODFIN-BETA-[A-F0-9]{8}(?:-[A-F0-9]{8}){3}$/);
  assert.equal(
    key,
    betaLicenseKeyForTester(
      "11111111-1111-4111-8111-111111111111",
      "a-secret-longer-than-twenty-four-characters",
    ),
  );
});

test("private INR 1 checkout requires an active allowlisted Max tester", () => {
  assert.equal(
    betaCheckoutEligibility({ status: "active", phase: "max", eligible: true }),
    true,
  );
  assert.equal(
    betaCheckoutEligibility({ status: "active", phase: "pro", eligible: true }),
    false,
  );
  assert.equal(
    betaCheckoutEligibility({ status: "paused", phase: "max", eligible: true }),
    false,
  );
  assert.equal(
    betaCheckoutEligibility({ status: "active", phase: "max", eligible: false }),
    false,
  );
});

test("feedback text is bounded and obvious secrets are rejected", () => {
  assert.equal(cleanText("a\u0000b\r\nc", 20), "ab\nc");
  assert.equal(containsSensitiveFeedback("GODFIN-BETA-AAAA-BBBB-CCCC-DDDD"), true);
  assert.equal(containsSensitiveFeedback("My account is 1234567890123456"), true);
  assert.equal(containsSensitiveFeedback("The button stayed disabled after I clicked it."), false);
});
