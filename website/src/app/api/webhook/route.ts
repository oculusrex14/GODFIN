import { NextResponse } from "next/server";
import type Stripe from "stripe";

import { sendLicenseEmail } from "@/lib/email";
import { serverEnv } from "@/lib/env";
import {
  hashLicenseKey,
  licenseKeyForSession,
  type LicenseTier,
} from "@/lib/license";
import { isProductCode, PRODUCTS } from "@/lib/products";
import { createAdminClient } from "@/lib/supabase/admin";
import { stripe } from "@/lib/stripe";

export const runtime = "nodejs";

async function provision(session: Stripe.Checkout.Session) {
  const productCode = session.metadata?.product_code;
  const userId = session.client_reference_id || session.metadata?.user_id;
  if (!isProductCode(productCode) || !userId) {
    throw new Error("Checkout metadata is incomplete.");
  }
  const product = PRODUCTS[productCode];
  if (session.currency !== "inr" || session.amount_total !== product.amount) {
    throw new Error("Checkout amount does not match the configured product.");
  }

  const tier = product.tier as LicenseTier | null;
  const licenseKey = tier
    ? licenseKeyForSession(
        session.id,
        tier,
        serverEnv.licenseSigningSecret(),
      )
    : null;
  const admin = createAdminClient();
  const { data, error } = await admin.rpc("provision_purchase", {
    p_checkout_session_id: session.id,
    p_user_id: userId,
    p_product_code: productCode,
    p_amount_total: session.amount_total,
    p_currency: session.currency,
    p_license_tier: tier,
    p_license_hash: licenseKey ? hashLicenseKey(licenseKey) : null,
    p_license_last4: licenseKey ? licenseKey.slice(-4) : null,
    p_credits: product.credits,
  });
  if (error) throw error;

  const provisioned = Array.isArray(data) ? data[0] : data;
  const email = session.customer_details?.email || session.customer_email;
  if (licenseKey && tier && email && !provisioned?.email_sent_at) {
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

export async function POST(request: Request) {
  const signature = request.headers.get("stripe-signature");
  if (!signature) {
    return NextResponse.json({ message: "Missing signature." }, { status: 400 });
  }

  let event: Stripe.Event;
  try {
    event = stripe().webhooks.constructEvent(
      await request.text(),
      signature,
      serverEnv.stripeWebhookSecret(),
    );
  } catch {
    return NextResponse.json({ message: "Invalid signature." }, { status: 400 });
  }

  try {
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
