import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import { afterEach, beforeEach, describe, it } from "node:test";

import {
  CashfreeApiError,
  cashfreeAmountToMinor,
  createCashfreeOrder,
  verifyCashfreeWebhook,
} from "@/lib/cashfree";

const ORIGINAL_FETCH = globalThis.fetch;
const SECRET = "cashfree-test-secret";

function signature(timestamp: string, rawBody: string): string {
  return createHmac("sha256", SECRET)
    .update(timestamp + rawBody, "utf8")
    .digest("base64");
}

beforeEach(() => {
  process.env.CASHFREE_CLIENT_ID = "cashfree-test-client";
  process.env.CASHFREE_CLIENT_SECRET = SECRET;
  process.env.CASHFREE_ENVIRONMENT = "sandbox";
  process.env.NEXT_PUBLIC_SITE_URL = "https://godfin.dev";
});

afterEach(() => {
  globalThis.fetch = ORIGINAL_FETCH;
});

describe("Cashfree webhook verification", () => {
  it("accepts a current, correctly signed exact raw body", () => {
    const rawBody = '{"type":"PAYMENT_SUCCESS_WEBHOOK","data":{"amount":4999}}';
    const now = 1_789_500_000_000;
    const timestamp = String(now - 1_000);
    assert.equal(
      verifyCashfreeWebhook({
        rawBody,
        signature: signature(timestamp, rawBody),
        timestamp,
        version: "2026-01-01",
        now,
      }),
      true,
    );
  });

  it("rejects changed payloads, unsupported versions, and stale timestamps", () => {
    const rawBody = '{"type":"PAYMENT_SUCCESS_WEBHOOK"}';
    const now = 1_789_500_000_000;
    const timestamp = String(now);
    const signed = signature(timestamp, rawBody);
    assert.equal(
      verifyCashfreeWebhook({
        rawBody: `${rawBody} `,
        signature: signed,
        timestamp,
        version: "2026-01-01",
        now,
      }),
      false,
    );
    assert.equal(
      verifyCashfreeWebhook({
        rawBody,
        signature: signed,
        timestamp,
        version: "2024-01-01",
        now,
      }),
      false,
    );
    const staleTimestamp = String(now - 5 * 60 * 1_000 - 1);
    assert.equal(
      verifyCashfreeWebhook({
        rawBody,
        signature: signature(staleTimestamp, rawBody),
        timestamp: staleTimestamp,
        version: "2026-01-01",
        now,
      }),
      false,
    );
  });
});

describe("Cashfree amount and order contracts", () => {
  it("converts provider major-unit values to integer minor units", () => {
    assert.equal(cashfreeAmountToMinor(4999), 499900);
    assert.equal(cashfreeAmountToMinor(10.34), 1034);
    assert.equal(cashfreeAmountToMinor(-1), null);
    assert.equal(cashfreeAmountToMinor("4999"), null);
  });

  it("creates a sandbox order with server-owned amount and callback URLs", async () => {
    let requestUrl = "";
    let requestInit: RequestInit | undefined;
    globalThis.fetch = async (input, init) => {
      requestUrl = String(input);
      requestInit = init;
      return new Response(
        JSON.stringify({
          cf_order_id: "12345",
          order_id: "godfin_00000000-0000-4000-8000-000000000001",
          order_amount: 4999,
          order_currency: "INR",
          order_status: "ACTIVE",
          payment_session_id: "session_test",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    };

    await createCashfreeOrder({
      orderId: "godfin_00000000-0000-4000-8000-000000000001",
      amountMinor: 499900,
      currency: "inr",
      customerId: "gf_test_customer",
      customerEmail: "buyer@example.test",
      productName: "GODFIN Pro lifetime desktop license",
      tags: {
        product_code: "pro",
        user_id: "66666666-6666-4666-8666-666666666666",
        pricing_country: "IN",
        pricing_version: "world-bank-icp-2021-v1",
      },
    });

    assert.equal(requestUrl, "https://sandbox.cashfree.com/pg/orders");
    assert.equal(requestInit?.method, "POST");
    const headers = requestInit?.headers as Record<string, string>;
    assert.equal(headers["x-api-version"], "2026-01-01");
    assert.equal(
      headers["x-idempotency-key"],
      "00000000-0000-4000-8000-000000000001",
    );
    const body = JSON.parse(String(requestInit?.body));
    assert.equal(body.order_amount, 4999);
    assert.equal(body.order_currency, "INR");
    assert.equal(
      body.order_meta.return_url,
      "https://godfin.dev/account?checkout=return&order_id=godfin_00000000-0000-4000-8000-000000000001",
    );
    assert.equal(body.order_meta.notify_url, "https://godfin.dev/api/webhook");
    assert.equal(body.customer_details.customer_phone, "9999999999");
  });

  it("surfaces a provider error without exposing credentials", async () => {
    globalThis.fetch = async () =>
      new Response(
        JSON.stringify({ code: "order_already_exists", message: "Duplicate order" }),
        { status: 409, headers: { "Content-Type": "application/json" } },
      );
    await assert.rejects(
      createCashfreeOrder({
        orderId: "godfin_00000000-0000-4000-8000-000000000001",
        amountMinor: 499900,
        currency: "inr",
        customerId: "gf_test_customer",
        customerEmail: "buyer@example.test",
        productName: "GODFIN Pro lifetime desktop license",
        tags: {},
      }),
      (error: unknown) =>
        error instanceof CashfreeApiError &&
        error.status === 409 &&
        error.code === "order_already_exists",
    );
  });
});
