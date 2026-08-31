import { createHmac } from "node:crypto";

import { NextResponse } from "next/server";

import { checkRateLimit, rateLimitResponse } from "@/lib/abuse-control";
import {
  BETA_CHECKOUT_AMOUNT_MINOR,
  BETA_CHECKOUT_CURRENCY,
  BETA_CHECKOUT_FLOW,
  BETA_CHECKOUT_PRODUCT_CODE,
} from "@/lib/beta-checkout";
import { betaPortalState } from "@/lib/beta-access";
import {
  cashfreeMode,
  createCashfreeOrder,
} from "@/lib/cashfree";
import { betaCheckoutConfigured, serverEnv } from "@/lib/env";
import { createAdminClient } from "@/lib/supabase/admin";
import { createSupabaseServerClient } from "@/lib/supabase/server";

export const runtime = "nodejs";

const UUID_V4 =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function json(body: Record<string, unknown>, status = 200) {
  return NextResponse.json(body, {
    status,
    headers: { "Cache-Control": "no-store" },
  });
}

export async function POST(request: Request) {
  try {
    if (!betaCheckoutConfigured()) {
      return json({ message: "The owner-controlled beta checkout test is closed." }, 503);
    }
    const addressLimit = await checkRateLimit(request, {
      bucket: "beta-checkout:address",
      limit: 10,
      windowSeconds: 60 * 60,
    });
    if (!addressLimit.allowed) return rateLimitResponse(addressLimit);

    const supabase = await createSupabaseServerClient();
    const { data: { user } } = (await supabase?.auth.getUser()) || {
      data: { user: null },
    };
    if (!user?.email) return json({ message: "Sign in to run the beta checkout test." }, 401);

    const userLimit = await checkRateLimit(request, {
      bucket: "beta-checkout:user",
      limit: 4,
      windowSeconds: 24 * 60 * 60,
      subject: `user:${user.id}`,
    });
    if (!userLimit.allowed) return rateLimitResponse(userLimit);

    const tester = await betaPortalState(user.id);
    if (!tester?.checkoutEligible) {
      return json({ message: "This account is not allowlisted for the private checkout test." }, 403);
    }
    if (tester.checkoutCompletedAt) {
      return json({ message: "This private INR 1 checkout test is already complete." }, 409);
    }

    const body = (await request.json().catch(() => ({}))) as {
      checkoutAttemptId?: unknown;
    };
    if (typeof body.checkoutAttemptId !== "string" || !UUID_V4.test(body.checkoutAttemptId)) {
      return json({ message: "Checkout attempt is invalid. Please try again." }, 400);
    }

    const orderId = `godfin_beta_${body.checkoutAttemptId}`;
    const admin = createAdminClient();
    const { error: insertError } = await admin
      .from("beta_checkout_attempts")
      .upsert(
        {
          beta_tester_id: tester.id,
          user_id: user.id,
          provider_order_id: orderId,
          amount_total: BETA_CHECKOUT_AMOUNT_MINOR,
          currency: BETA_CHECKOUT_CURRENCY,
          idempotency_key: body.checkoutAttemptId,
        },
        { onConflict: "provider_order_id", ignoreDuplicates: true },
      );
    if (insertError) throw insertError;
    const { data: attempt, error: attemptError } = await admin
      .from("beta_checkout_attempts")
      .select("id,beta_tester_id,user_id,status")
      .eq("provider_order_id", orderId)
      .single();
    if (attemptError) throw attemptError;
    if (attempt.beta_tester_id !== tester.id || attempt.user_id !== user.id) {
      return json({ message: "Checkout attempt is invalid. Please try again." }, 409);
    }

    const customerId = `gf_beta_${createHmac("sha256", serverEnv.abuseHashSecret())
      .update(`cashfree-beta-customer:${user.id}`)
      .digest("hex")
      .slice(0, 24)}`;
    const order = await createCashfreeOrder({
      orderId,
      amountMinor: BETA_CHECKOUT_AMOUNT_MINOR,
      currency: BETA_CHECKOUT_CURRENCY,
      customerId,
      customerEmail: user.email,
      productName: "GODFIN private beta checkout-flow validation (INR 1)",
      returnPath: "/beta",
      tags: {
        product_code: BETA_CHECKOUT_PRODUCT_CODE,
        flow: BETA_CHECKOUT_FLOW,
        beta_tester_id: tester.id,
        user_id: user.id,
      },
    });
    if (!order.payment_session_id || order.order_id !== orderId) {
      throw new Error("Cashfree did not return a usable beta payment session.");
    }
    const { error: updateError } = await admin
      .from("beta_checkout_attempts")
      .update({
        provider_order_reference_id: String(order.cf_order_id),
        updated_at: new Date().toISOString(),
      })
      .eq("provider_order_id", orderId)
      .eq("user_id", user.id);
    if (updateError) throw updateError;

    return json({
      paymentSessionId: order.payment_session_id,
      orderId,
      mode: cashfreeMode(),
      amountMinor: BETA_CHECKOUT_AMOUNT_MINOR,
      currency: BETA_CHECKOUT_CURRENCY,
      createsPurchase: false,
    });
  } catch (error) {
    console.error("Private beta checkout creation failed", {
      errorType: error instanceof Error ? error.name : "UnknownError",
    });
    return json({ message: "The private checkout test is temporarily unavailable." }, 503);
  }
}
