import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  betaOrderIdFromWebhook,
  betaStatusFromWebhook,
  isBetaCheckoutOrderId,
  reviewBetaCheckout,
} from "@/lib/beta-checkout";

const orderId = "godfin_beta_00000000-0000-4000-8000-000000000001";

describe("private beta Cashfree contracts", () => {
  it("recognizes only the dedicated beta order namespace", () => {
    assert.equal(isBetaCheckoutOrderId(orderId), true);
    assert.equal(isBetaCheckoutOrderId("godfin_00000000-0000-4000-8000-000000000001"), false);
    assert.equal(
      betaOrderIdFromWebhook({
        type: "PAYMENT_SUCCESS_WEBHOOK",
        data: { order: { order_id: orderId } },
      }),
      orderId,
    );
    assert.equal(
      betaOrderIdFromWebhook({
        type: "PAYMENT_SUCCESS_WEBHOOK",
        data: { order: { order_id: "godfin_not_beta" } },
      }),
      null,
    );
  });

  it("maps signed non-success event shapes without treating them as purchases", () => {
    assert.equal(betaStatusFromWebhook({ type: "PAYMENT_FAILED_WEBHOOK" }), "failed");
    assert.equal(betaStatusFromWebhook({ type: "PAYMENT_USER_DROPPED_WEBHOOK" }), "abandoned");
    assert.equal(
      betaStatusFromWebhook({
        type: "REFUND_STATUS_WEBHOOK",
        data: { refund: { refund_status: "SUCCESS" } },
      }),
      "refunded",
    );
    assert.equal(
      betaStatusFromWebhook({
        type: "DISPUTE_CLOSED",
        data: { dispute: { dispute_status: "DISPUTE_LOST" } },
      }),
      "dispute_lost",
    );
  });

  it("requires exact INR 1, identity, email, and private-flow tags", () => {
    const base = {
      order: {
        cf_order_id: "cf-1",
        order_id: orderId,
        order_amount: 1,
        order_currency: "INR",
        order_status: "PAID",
        customer_details: { customer_email: "tester@example.test" },
        order_tags: {
          product_code: "godfin_beta_checkout_test",
          flow: "beta_checkout_validation",
          beta_tester_id: "11111111-1111-4111-8111-111111111111",
          user_id: "22222222-2222-4222-8222-222222222222",
        },
      },
      payment: {
        cf_payment_id: "payment-1",
        payment_status: "SUCCESS",
        payment_amount: 1,
        payment_currency: "INR",
      },
      orderId,
      testerId: "11111111-1111-4111-8111-111111111111",
      userId: "22222222-2222-4222-8222-222222222222",
      accountEmail: "tester@example.test",
    } as const;
    assert.deepEqual(reviewBetaCheckout(base), { verified: true, reason: null });
    assert.match(
      reviewBetaCheckout({
        ...base,
        order: { ...base.order, order_amount: 4999 },
      }).reason || "",
      /order_amount_mismatch/,
    );
  });
});
