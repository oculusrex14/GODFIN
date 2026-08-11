import { createHash } from "node:crypto";

import { NextResponse } from "next/server";
import type Stripe from "stripe";

import { sendLicenseEmail } from "@/lib/email";
import { serverEnv } from "@/lib/env";
import {
  hashLicenseKey,
  licenseKeyForSession,
  type LicenseTier,
} from "@/lib/license";
import {
  isProductCode,
  PRODUCTS,
  stripePriceIdForEnvironment,
} from "@/lib/products";
import {
  isLicenseProduct,
  PPP_PRICE_VERSION,
  regionalPrice,
} from "@/lib/regional-pricing";
import { createAdminClient } from "@/lib/supabase/admin";
import { stripe } from "@/lib/stripe";

export const runtime = "nodejs";

const PAYMENT_EVENT_TYPES = new Set<Stripe.Event.Type>([
  "checkout.session.completed",
  "checkout.session.async_payment_succeeded",
  "checkout.session.async_payment_failed",
  "refund.created",
  "refund.updated",
  "refund.failed",
  "charge.refunded",
  "charge.dispute.created",
  "charge.dispute.updated",
  "charge.dispute.closed",
  "charge.dispute.funds_withdrawn",
  "charge.dispute.funds_reinstated",
]);

type StripeObject = { id: string };

function relatedId(value: string | StripeObject | null | undefined): string | null {
  if (typeof value === "string") return value;
  return value?.id || null;
}

function normalizedCountry(value: string | null | undefined): string | null {
  const country = value?.trim().toUpperCase();
  return country && /^[A-Z]{2}$/.test(country) ? country : null;
}

function pricingReview({
  session,
  expectedCurrency,
  expectedSubtotal,
  expectedPriceId,
  pricingCountry,
  actualPriceId,
}: {
  session: Stripe.Checkout.Session;
  expectedCurrency: string;
  expectedSubtotal: number;
  expectedPriceId: string;
  pricingCountry: "IN" | "US";
  actualPriceId: string | null;
}): { verified: boolean; reason: string | null; billingCountry: string | null } {
  const billingCountry = normalizedCountry(
    session.customer_details?.address?.country,
  );
  const failures: string[] = [];
  if (session.currency !== expectedCurrency) failures.push("currency_mismatch");
  if (session.amount_subtotal !== expectedSubtotal) failures.push("subtotal_mismatch");
  if (actualPriceId !== expectedPriceId) failures.push("price_id_mismatch");
  if (session.metadata?.pricing_version !== PPP_PRICE_VERSION) {
    failures.push("pricing_version_mismatch");
  }
  if (session.automatic_tax?.enabled !== true) failures.push("tax_not_enabled");
  if (!billingCountry) {
    failures.push("billing_country_missing");
  } else if (
    (pricingCountry === "IN" && billingCountry !== "IN") ||
    (pricingCountry === "US" && billingCountry === "IN")
  ) {
    failures.push("billing_country_mismatch");
  }
  return {
    verified: failures.length === 0,
    reason: failures.length ? failures.join(",") : null,
    billingCountry,
  };
}

async function hydratedSession(
  incoming: Stripe.Checkout.Session,
): Promise<Stripe.Checkout.Session> {
  return stripe().checkout.sessions.retrieve(incoming.id, {
    expand: ["line_items.data.price", "payment_intent.latest_charge"],
  });
}

async function provision(incoming: Stripe.Checkout.Session) {
  const session = await hydratedSession(incoming);
  const productCode = session.metadata?.product_code;
  const userId = session.client_reference_id || session.metadata?.user_id;
  if (!isProductCode(productCode) || !isLicenseProduct(productCode) || !userId) {
    throw new Error("Checkout metadata is incomplete.");
  }
  const product = PRODUCTS[productCode];
  const expected = regionalPrice(
    productCode,
    session.metadata?.pricing_country,
    false,
  );
  const expectedPriceId = stripePriceIdForEnvironment(expected.priceEnv);
  const lineItems = session.line_items?.data || [];
  const lineItem = lineItems.length === 1 ? lineItems[0] : null;
  const actualPriceId = relatedId(lineItem?.price);
  const review = pricingReview({
    session,
    expectedCurrency: expected.currency,
    expectedSubtotal: expected.amount,
    expectedPriceId,
    pricingCountry: expected.country,
    actualPriceId,
  });
  if (lineItem?.quantity !== 1) {
    review.verified = false;
    review.reason = [review.reason, "invalid_quantity"].filter(Boolean).join(",");
  }
  if (session.payment_status !== "paid" || session.amount_total === null) {
    throw new Error("Checkout is not paid.");
  }

  const tier = product.tier as LicenseTier;
  const licenseKey = licenseKeyForSession(
    session.id,
    tier,
    serverEnv.licenseSigningSecret(),
  );
  const paymentIntent = session.payment_intent;
  const paymentIntentId = relatedId(paymentIntent);
  const chargeId =
    paymentIntent && typeof paymentIntent !== "string"
      ? relatedId(paymentIntent.latest_charge)
      : null;
  const admin = createAdminClient();
  const { data, error } = await admin.rpc("provision_purchase", {
    p_checkout_session_id: session.id,
    p_payment_intent_id: paymentIntentId,
    p_charge_id: chargeId,
    p_stripe_customer_id: relatedId(session.customer),
    p_user_id: userId,
    p_product_code: productCode,
    p_amount_total: session.amount_total,
    p_currency: session.currency,
    p_license_tier: tier,
    p_license_hash: hashLicenseKey(licenseKey),
    p_license_last4: licenseKey.slice(-4),
    p_credits: 0,
    p_billing_country: review.billingCountry,
    p_pricing_country: expected.country,
    p_pricing_version: session.metadata?.pricing_version || null,
    p_pricing_verified: review.verified,
    p_pricing_review_reason: review.reason,
  });
  if (error) throw error;

  const provisioned = Array.isArray(data) ? data[0] : data;
  const email = session.customer_details?.email || session.customer_email;
  if (
    review.verified &&
    provisioned?.license_status === "active" &&
    email &&
    !provisioned?.email_sent_at
  ) {
    await sendLicenseEmail({
      to: email,
      licenseKey,
      tier,
      idempotencyKey: `license:${session.id}`,
    });
    await admin
      .from("purchases")
      .update({ email_sent_at: new Date().toISOString() })
      .eq("checkout_session_id", session.id);
  }
}

function paymentEventFields(event: Stripe.Event) {
  const object = event.data.object;
  const base = {
    p_stripe_event_id: event.id,
    p_event_type: event.type,
    p_object_id: relatedId(object as StripeObject),
    p_checkout_session_id: null as string | null,
    p_payment_intent_id: null as string | null,
    p_charge_id: null as string | null,
    p_refund_id: null as string | null,
    p_dispute_id: null as string | null,
    p_amount: null as number | null,
    p_currency: null as string | null,
    p_event_status: null as string | null,
    p_reason: null as string | null,
  };
  if (event.type.startsWith("checkout.session.")) {
    const session = object as Stripe.Checkout.Session;
    return {
      ...base,
      p_checkout_session_id: session.id,
      p_payment_intent_id: relatedId(session.payment_intent),
      p_amount: session.amount_total,
      p_currency: session.currency,
      p_event_status:
        event.type === "checkout.session.async_payment_failed"
          ? "failed"
          : session.payment_status,
    };
  }
  if (event.type.startsWith("refund.")) {
    const refund = object as Stripe.Refund;
    return {
      ...base,
      p_payment_intent_id: relatedId(refund.payment_intent),
      p_charge_id: relatedId(refund.charge),
      p_refund_id: refund.id,
      p_amount: refund.amount,
      p_currency: refund.currency,
      p_event_status: refund.status,
      p_reason: refund.failure_reason || refund.pending_reason || refund.reason,
    };
  }
  if (event.type === "charge.refunded") {
    const charge = object as Stripe.Charge;
    return {
      ...base,
      p_payment_intent_id: relatedId(charge.payment_intent),
      p_charge_id: charge.id,
      p_amount: charge.amount_refunded,
      p_currency: charge.currency,
      p_event_status: charge.refunded ? "refunded" : "partially_refunded",
    };
  }
  const dispute = object as Stripe.Dispute;
  return {
    ...base,
    p_payment_intent_id: relatedId(dispute.payment_intent),
    p_charge_id: relatedId(dispute.charge),
    p_dispute_id: dispute.id,
    p_amount: dispute.amount,
    p_currency: dispute.currency,
    p_event_status: dispute.status,
    p_reason: dispute.reason,
  };
}

async function recordPaymentEvent(event: Stripe.Event, payloadSha256: string) {
  if (!PAYMENT_EVENT_TYPES.has(event.type)) return;
  const admin = createAdminClient();
  const { error } = await admin.rpc("record_payment_event", {
    ...paymentEventFields(event),
    p_payload_sha256: payloadSha256,
    p_occurred_at: new Date(event.created * 1000).toISOString(),
  });
  if (error) throw error;
}

export async function POST(request: Request) {
  const signature = request.headers.get("stripe-signature");
  if (!signature) {
    return NextResponse.json({ message: "Missing signature." }, { status: 400 });
  }

  const rawBody = await request.text();
  let event: Stripe.Event;
  try {
    event = stripe().webhooks.constructEvent(
      rawBody,
      signature,
      serverEnv.stripeWebhookSecret(),
    );
  } catch {
    return NextResponse.json({ message: "Invalid signature." }, { status: 400 });
  }

  try {
    await recordPaymentEvent(
      event,
      createHash("sha256").update(rawBody).digest("hex"),
    );
    if (
      event.type === "checkout.session.completed" ||
      event.type === "checkout.session.async_payment_succeeded"
    ) {
      const session = event.data.object as Stripe.Checkout.Session;
      if (session.payment_status === "paid") await provision(session);
    }
    return NextResponse.json({ received: true });
  } catch (error) {
    console.error("Stripe fulfillment failed", error);
    return NextResponse.json(
      { message: "Fulfillment failed and will be retried." },
      { status: 500 },
    );
  }
}
