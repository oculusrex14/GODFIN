import assert from "node:assert/strict";
import test from "node:test";

import {
  MAX_WEBHOOK_BODY_BYTES,
  readCappedWebhookBody,
} from "./webhook-body";

test("webhook body reader accepts a bounded UTF-8 body", async () => {
  const request = new Request("https://godfin.dev/api/webhook", {
    method: "POST",
    body: '{"type":"PAYMENT_SUCCESS_WEBHOOK"}',
  });
  assert.equal(
    await readCappedWebhookBody(request),
    '{"type":"PAYMENT_SUCCESS_WEBHOOK"}',
  );
});

test("webhook body reader rejects declared and streamed oversized bodies", async () => {
  const declared = new Request("https://godfin.dev/api/webhook", {
    method: "POST",
    headers: { "content-length": String(MAX_WEBHOOK_BODY_BYTES + 1) },
    body: "{}",
  });
  await assert.rejects(readCappedWebhookBody(declared), /too large/i);

  const streamed = new Request("https://godfin.dev/api/webhook", {
    method: "POST",
    body: "x".repeat(65),
  });
  await assert.rejects(readCappedWebhookBody(streamed, 64), /too large/i);
});

test("webhook body reader rejects invalid UTF-8", async () => {
  const request = new Request("https://godfin.dev/api/webhook", {
    method: "POST",
    body: new Uint8Array([0xc3, 0x28]),
  });
  await assert.rejects(readCappedWebhookBody(request), /encoded data/i);
});
