import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { resolveLicenseCheckout } from "@/lib/license-upgrades";
import { regionalPrice } from "@/lib/regional-pricing";

const PRO = {
  id: "11111111-1111-4111-8111-111111111111",
  tier: "pro",
  status: "active",
};

describe("lifetime license checkout state machine", () => {
  it("supports Free to Pro and Free to Max as base purchases", () => {
    assert.deepEqual(resolveLicenseCheckout("pro", []), {
      ok: true,
      productCode: "pro",
      purchaseKind: "base",
      upgradeLicenseId: null,
    });
    assert.deepEqual(resolveLicenseCheckout("max", []), {
      ok: true,
      productCode: "max",
      purchaseKind: "base",
      upgradeLicenseId: null,
    });
  });

  it("turns Pro to Max into an in-place upgrade", () => {
    assert.deepEqual(resolveLicenseCheckout("max", [PRO]), {
      ok: true,
      productCode: "pro_to_max",
      purchaseKind: "upgrade",
      upgradeLicenseId: PRO.id,
    });
    assert.equal(regionalPrice("pro_to_max", "IN", false).amount, 500000);
    assert.equal(regionalPrice("pro_to_max", "US", false).amount, 10000);
  });

  it("rejects duplicate plans, inactive licenses, and ambiguous ownership", () => {
    assert.equal(resolveLicenseCheckout("pro", [PRO]).ok, false);
    assert.equal(
      resolveLicenseCheckout("max", [{ ...PRO, tier: "max" }]).ok,
      false,
    );
    assert.equal(
      resolveLicenseCheckout("max", [{ ...PRO, status: "suspended" }]).ok,
      false,
    );
    assert.equal(resolveLicenseCheckout("max", [PRO, { ...PRO, id: "other" }]).ok, false);
  });
});
