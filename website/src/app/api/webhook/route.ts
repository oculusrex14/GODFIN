import { createHash, randomUUID } from "node:crypto";

import { NextResponse } from "next/server";

import {
  cashfreeAmountToMinor,
  getCashfreeOrder,
  getCashfreePayments,
  verifyCashfreeWebhook,
  type CashfreeOrder,
  type CashfreePayment,
} from "@/lib/cashfree";
import { sendLicenseEmail, sendPlanUpgradeEmail } from "@/lib/email";
import { serverEnv } from "@/lib/env";
import {
  hashLicenseKey,
  licenseKeyForSession,
  type LicenseTier,
} from "@/lib/license";
import { isProductCode, PRODUCTS } from "@/lib/products";
import {
  isLicenseProduct,
  PPP_PRICE_VERSION,
  regionalPrice,
} from "@/lib/regional-pricing";
import { createAdminClient } from "@/lib/supabase/admin";
import { checkRateLimit, rateLimitResponse } from "@/lib/abuse-control";
import {
  readCappedWebhookBody,
  WebhookPayloadTooLarge,
} from "@/lib/webhook-body";

export const runtime = "nodejs";

const CASHFREE_EVENT_TYPES = new Set([
  "PAYMENT_SUCCESS_WEBHOOK",
  "PAYMENT_FAILED_WEBHOOK",
  "PAYMENT_USER_DROPPED_WEBHOOK",
  "REFUND_STATUS_WEBHOOK",
  "AUTO_REFUND_STATUS_WEBHOOK",
  "DISPUTE_CREATED",
  "DISPUTE_UPDATED",
  "DISPUTE_CLOSED",
]);
const EMAIL_CLAIM_TTL_MS = 10 * 60 * 1000;

type JsonRecord = Record<string, unknown>;

function record(value: unknown): JsonRecord {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as JsonRecord)
    : {};
}

function text(value: unknown): string | null {
  if (typeof value === "string" && value.trim()) return value.trim();
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return null;
}

function normalizedCurrency(value: unknown): string | null {
  const currency = text(value)?.toLowerCase();
  return currency && /^[a-z]{3}$/.test(currency) ? currency : null;
}

function occurredAt(value: unknown): string | null {
  const parsed = Date.parse(text(value) || "");
  return Number.isFinite(parsed) ? new Date(parsed).toISOString() : null;
}

function eventIdentity(
  idempotencyKey: string | null,
  rawBody: string,
): string {
  const safeHeader = idempotencyKey?.trim().slice(0, 180);
  return `cashfree:${safeHeader || createHash("sha256").update(rawBody).digest("hex")}`;
}

async function claimPurchaseEmail(
  admin: ReturnType<typeof createAdminClient>,
  purchaseId: string,
): Promise<string | null> {
  const claimedAt = new Date().toISOString();
  const staleBefore = new Date(Date.now() - EMAIL_CLAIM_TTL_MS).toISOString();
  const { data, error } = await admin
    .from("purchases")
    .update({ email_claimed_at: claimedAt })
    .eq("id", purchaseId)
    .is("email_sent_at", null)
    .or(`email_claimed_at.is.null,email_claimed_at.lt.${staleBefore}`)
    .select("id")
    .maybeSingle();
  if (error) throw error;
  return data?.id ? claimedAt : null;
}

async function finishPurchaseEmailClaim({
  admin,
  purchaseId,
  claimedAt,
  delivered,
}: {
  admin: ReturnType<typeof createAdminClient>;
  purchaseId: string;
  claimedAt: string;
  delivered: boolean;
}) {
  const { error } = await admin
    .from("purchases")
    .update(
      delivered
        ? { email_sent_at: new Date().toISOString(), email_claimed_at: null }
        : { email_claimed_at: null },
    )
    .eq("id", purchaseId)
    .eq("email_claimed_at", claimedAt);
  if (error) throw error;
}

function paymentEventFields(event: JsonRecord) {
  const type = text(event.type) || "";
  const data = record(event.data);
  const base = {
    p_event_type: type,
    p_object_id: null as string | null,
    p_provider_order_id: null as string | null,
    p_provider_payment_id: null as string | null,
    p_provider_refund_id: null as string | null,
    p_provider_dispute_id: null as string | null,
    p_amount: null as number | null,
    p_currency: null as string | null,
    p_event_status: null as string | null,
    p_reason: null as string | null,
  };

  if (type.startsWith("PAYMENT_")) {
    const order = record(data.order);
    const payment = record(data.payment);
    const paymentId = text(payment.cf_payment_id);
    return {
      ...base,
      p_object_id: paymentId,
      p_provider_order_id: text(order.order_id),
      p_provider_payment_id: paymentId,
      p_amount: cashfreeAmountToMinor(payment.payment_amount),
      p_currency: normalizedCurrency(payment.payment_currency),
      p_event_status: text(payment.payment_status),
      p_reason: text(payment.payment_message),
    };
  }

  if (type === "REFUND_STATUS_WEBHOOK" || type === "AUTO_REFUND_STATUS_WEBHOOK") {
    const refund = record(
      type === "AUTO_REFUND_STATUS_WEBHOOK" ? data.auto_refund : data.refund,
    );
    const refundId = text(refund.refund_id) || text(refund.cf_refund_id);
    return {
      ...base,
      p_object_id: refundId,
      p_provider_order_id: text(refund.order_id),
      p_provider_payment_id: text(refund.cf_payment_id),
      p_provider_refund_id: refundId,
      p_amount: cashfreeAmountToMinor(refund.refund_amount),
      p_currency: normalizedCurrency(refund.refund_currency),
      p_event_status: text(refund.refund_status),
      p_reason: text(refund.refund_reason) || text(refund.status_description),
    };
  }

  const dispute = record(data.dispute);
  const order = record(data.order_details);
  const disputeId = text(dispute.dispute_id);
  return {
    ...base,
    p_object_id: disputeId,
    p_provider_order_id: text(order.order_id),
    p_provider_payment_id: text(order.cf_payment_id),
    p_provider_dispute_id: disputeId,
    p_amount: cashfreeAmountToMinor(dispute.dispute_amount),
    p_currency:
      normalizedCurrency(dispute.dispute_amount_currency) ||
      normalizedCurrency(order.payment_currency),
    p_event_status: text(dispute.dispute_status),
    p_reason:
      text(dispute.reason_description) || text(dispute.cf_dispute_remarks),
  };
}

function purchaseReview({
  order,
  payment,
  expectedAmount,
  expectedCurrency,
  pricingCountry,
  pricingVersion,
  accountEmail,
}: {
  order: CashfreeOrder;
  payment: CashfreePayment;
  expectedAmount: number;
  expectedCurrency: string;
  pricingCountry: "IN" | "US";
  pricingVersion: string | null;
  accountEmail: string;
}): { verified: boolean; reason: string | null } {
  const failures: string[] = [];
  if (order.order_status.toUpperCase() !== "PAID") failures.push("order_not_paid");
  if (payment.payment_status.toUpperCase() !== "SUCCESS") {
    failures.push("payment_not_successful");
  }
  if (cashfreeAmountToMinor(order.order_amount) !== expectedAmount) {
    failures.push("order_amount_mismatch");
  }
  if (cashfreeAmountToMinor(payment.payment_amount) !== expectedAmount) {
    failures.push("payment_amount_mismatch");
  }
  if (order.order_currency.toLowerCase() !== expectedCurrency) {
    failures.push("order_currency_mismatch");
  }
  if (payment.payment_currency.toLowerCase() !== expectedCurrency) {
    failures.push("payment_currency_mismatch");
  }
  if (pricingVersion !== PPP_PRICE_VERSION) failures.push("pricing_version_mismatch");
  if (
    order.customer_details?.customer_email?.trim().toLowerCase() !==
    accountEmail.trim().toLowerCase()
  ) {
    failures.push("account_email_mismatch");
  }
  // India is the only checkout region enabled by default. A future global
  // rollout must add an authoritative billing-country signal before PPP is
  // enabled; a browser or edge country alone is not enough to authorize price.
  if (pricingCountry !== "IN") failures.push("billing_country_unverified");
  return {
    verified: failures.length === 0,
    reason: failures.length ? failures.join(",") : null,
  };
}

async function provisionCashfreePurchase(incoming: JsonRecord) {
  const incomingData = record(incoming.data);
  const incomingOrder = record(incomingData.order);
  const incomingPayment = record(incomingData.payment);
  const orderId = text(incomingOrder.order_id);
  const incomingPaymentId = text(incomingPayment.cf_payment_id);
  if (!orderId || !incomingPaymentId) {
    throw new Error("Cashfree payment webhook is missing order identifiers.");
  }

  const [order, payments] = await Promise.all([
    getCashfreeOrder(orderId),
    getCashfreePayments(orderId),
  ]);
  const payment = payments.find(
    (candidate) => String(candidate.cf_payment_id) === incomingPaymentId,
  );
  if (!payment) throw new Error("Cashfree payment could not be revalidated.");

  const productCode = order.order_tags?.product_code;
  const userId = order.order_tags?.user_id;
  const pricingCountry = order.order_tags?.pricing_country;
  const pricingVersion = order.order_tags?.pricing_version || null;
  const purchaseKind = order.order_tags?.purchase_kind;
  const targetTier = order.order_tags?.target_tier;
  const upgradeLicenseId = order.order_tags?.upgrade_license_id || null;
  if (
    !isProductCode(productCode) ||
    !isLicenseProduct(productCode) ||
    !userId ||
    !/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(userId)
  ) {
    throw new Error("Cashfree order metadata is incomplete.");
  }
  const isUpgrade = productCode === "pro_to_max";
  if (
    purchaseKind !== (isUpgrade ? "upgrade" : "base") ||
    targetTier !== PRODUCTS[productCode].tier ||
    (isUpgrade &&
      (!upgradeLicenseId ||
        !/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(
          upgradeLicenseId,
        ))) ||
    (!isUpgrade && upgradeLicenseId !== null)
  ) {
    throw new Error("Cashfree order upgrade metadata is invalid.");
  }

  const expected = regionalPrice(productCode, pricingCountry, false);
  const admin = createAdminClient();
  const { data: account, error: accountError } =
    await admin.auth.admin.getUserById(userId);
  if (accountError || !account.user?.email) {
    throw accountError || new Error("Purchase account was not found.");
  }
  const review = purchaseReview({
    order,
    payment,
    expectedAmount: expected.amount,
    expectedCurrency: expected.currency,
    pricingCountry: expected.country,
    pricingVersion,
    accountEmail: account.user.email,
  });

  const tier = PRODUCTS[productCode].tier as LicenseTier;
  const licenseKey = isUpgrade
    ? null
    : licenseKeyForSession(
        order.order_id,
        tier,
        serverEnv.licenseSigningSecret(),
      );
  const { data, error } = await admin.rpc("provision_cashfree_purchase", {
    p_order_id: order.order_id,
    p_cf_order_id: String(order.cf_order_id),
    p_cf_payment_id: String(payment.cf_payment_id),
    p_cf_customer_id: order.customer_details?.customer_id || null,
    p_user_id: userId,
    p_product_code: productCode,
    p_amount_total: expected.amount,
    p_currency: expected.currency,
    p_license_tier: tier,
    p_license_hash: licenseKey ? hashLicenseKey(licenseKey) : null,
    p_license_last4: licenseKey ? licenseKey.slice(-4) : null,
    p_billing_country: expected.country === "IN" ? "IN" : null,
    p_pricing_country: expected.country,
    p_pricing_version: pricingVersion,
    p_pricing_verified: review.verified,
    p_pricing_review_reason: review.reason,
    p_purchase_kind: purchaseKind,
    p_upgrade_license_id: upgradeLicenseId,
  });
  if (error) throw error;

  const provisioned = Array.isArray(data) ? data[0] : data;
  if (
    review.verified &&
    provisioned?.license_status === "active" &&
    !provisioned?.email_sent_at &&
    typeof provisioned?.purchase_id === "string"
  ) {
    const claimedAt = await claimPurchaseEmail(admin, provisioned.purchase_id);
    if (!claimedAt) return;
    try {
      if (isUpgrade) {
        await sendPlanUpgradeEmail({
          to: account.user.email,
          idempotencyKey: `cashfree-upgrade:${order.order_id}`,
        });
      } else if (licenseKey) {
        await sendLicenseEmail({
          to: account.user.email,
          licenseKey,
          tier,
          idempotencyKey: `cashfree-license:${order.order_id}`,
        });
      }
      await finishPurchaseEmailClaim({
        admin,
        purchaseId: provisioned.purchase_id,
        claimedAt,
        delivered: true,
      });
    } catch (error) {
      try {
        await finishPurchaseEmailClaim({
          admin,
          purchaseId: provisioned.purchase_id,
          claimedAt,
          delivered: false,
        });
      } catch {
        // A crashed or failed release is recoverable after the ten-minute
        // claim lease. Resend's idempotency key prevents duplicate delivery.
      }
      throw error;
    }
  }
}

async function recordCashfreeEvent({
  event,
  providerEventId,
  payloadSha256,
}: {
  event: JsonRecord;
  providerEventId: string;
  payloadSha256: string;
}) {
  const eventType = text(event.type) || "";
  if (!CASHFREE_EVENT_TYPES.has(eventType)) return;
  const eventTime = occurredAt(event.event_time);
  if (!eventTime) throw new Error("Cashfree event time is invalid.");
  const admin = createAdminClient();
  const { error } = await admin.rpc("record_cashfree_payment_event", {
    p_provider_event_id: providerEventId,
    ...paymentEventFields(event),
    p_payload_sha256: payloadSha256,
    p_occurred_at: eventTime,
  });
  if (error) throw error;
}

export async function POST(request: Request) {
  const requestId = randomUUID();
  let rawBody: string;
  try {
    rawBody = await readCappedWebhookBody(request);
  } catch (error) {
    const tooLarge = error instanceof WebhookPayloadTooLarge;
    console.warn("Cashfree webhook body rejected", {
      requestId,
      reason: tooLarge ? "payload_too_large" : "invalid_encoding",
    });
    return NextResponse.json(
      { message: tooLarge ? "Payload too large." : "Invalid payload." },
      { status: tooLarge ? 413 : 400 },
    );
  }
  let signatureValid = false;
  try {
    signatureValid = verifyCashfreeWebhook({
      rawBody,
      signature: request.headers.get("x-webhook-signature"),
      timestamp: request.headers.get("x-webhook-timestamp"),
      version: request.headers.get("x-webhook-version"),
    });
  } catch (error) {
    console.warn("Cashfree webhook signature check failed safely", {
      requestId,
      errorType: error instanceof Error ? error.name : "UnknownError",
    });
    signatureValid = false;
  }
  if (!signatureValid) {
    console.warn("Cashfree webhook signature rejected", {
      requestId,
      reason: "invalid_signature",
    });
    return NextResponse.json({ message: "Invalid signature." }, { status: 400 });
  }

  const providerEventId = eventIdentity(
    request.headers.get("x-idempotency-key"),
    rawBody,
  );
  try {
    const limit = await checkRateLimit(request, {
      bucket: "cashfree-webhook",
      limit: 600,
      windowSeconds: 60,
    });
    if (!limit.allowed) {
      return rateLimitResponse(limit, "Webhook rate limit exceeded.");
    }
  } catch {
    console.error("Cashfree webhook abuse control unavailable", { requestId });
    return NextResponse.json(
      { message: "Webhook processing is temporarily unavailable." },
      { status: 503 },
    );
  }

  let event: JsonRecord;
  try {
    event = record(JSON.parse(rawBody));
  } catch {
    return NextResponse.json({ message: "Invalid payload." }, { status: 400 });
  }

  const eventType = text(event.type) || "";
  if (!CASHFREE_EVENT_TYPES.has(eventType)) {
    return NextResponse.json({ received: true, ignored: true });
  }

  try {
    await recordCashfreeEvent({
      event,
      providerEventId,
      payloadSha256: createHash("sha256").update(rawBody).digest("hex"),
    });
    if (eventType === "PAYMENT_SUCCESS_WEBHOOK") {
      await provisionCashfreePurchase(event);
    }
    return NextResponse.json({ received: true });
  } catch (error) {
    console.error("Cashfree fulfillment failed", {
      requestId,
      eventType,
      errorType: error instanceof Error ? error.name : "UnknownError",
    });
    return NextResponse.json(
      { message: "Fulfillment failed and will be retried." },
      { status: 500 },
    );
  }
}
