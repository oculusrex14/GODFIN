import { createHmac } from "node:crypto";

import { NextResponse } from "next/server";

import { checkRateLimit, rateLimitResponse } from "@/lib/abuse-control";
import {
  cashfreeMode,
  createCashfreeOrder,
} from "@/lib/cashfree";
import { commerceConfigured, serverEnv } from "@/lib/env";
import {
  isProductCode,
  isRetiredHostedCreditCode,
  PRODUCTS,
} from "@/lib/products";
import {
  regionalPrice,
  requestPricingCountry,
} from "@/lib/regional-pricing";
import { createSupabaseServerClient } from "@/lib/supabase/server";

export const runtime = "nodejs";

export async function POST(request: Request) {
  try {
    if (!commerceConfigured()) {
      return NextResponse.json(
        {
          message:
            "Checkout is closed until verified support and privacy contacts are configured.",
        },
        { status: 503 },
      );
    }
    const addressLimit = await checkRateLimit(request, {
      bucket: "checkout:address",
      limit: 20,
      windowSeconds: 60 * 60,
    });
    if (!addressLimit.allowed) return rateLimitResponse(addressLimit);
    const supabase = await createSupabaseServerClient();
    if (!supabase) {
      return NextResponse.json(
        { message: "Website authentication is not configured." },
        { status: 503 },
      );
    }
    const {
      data: { user },
    } = await supabase.auth.getUser();
    if (!user?.email) {
      return NextResponse.json(
        { message: "Sign in before starting checkout." },
        { status: 401 },
      );
    }
    const userLimit = await checkRateLimit(request, {
      bucket: "checkout:user",
      limit: 10,
      windowSeconds: 60 * 60,
      subject: `user:${user.id}`,
    });
    if (!userLimit.allowed) return rateLimitResponse(userLimit);

    const body = (await request.json()) as {
      product?: unknown;
      checkoutAttemptId?: unknown;
    };
    if (isRetiredHostedCreditCode(body.product)) {
      return NextResponse.json(
        {
          message:
            "Hosted AI credit packs are not available because GODFIN does not operate a hosted credit-consumption service.",
        },
        { status: 410 },
      );
    }
    if (!isProductCode(body.product)) {
      return NextResponse.json({ message: "Unknown product." }, { status: 400 });
    }
    if (
      typeof body.checkoutAttemptId !== "string" ||
      !/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(
        body.checkoutAttemptId,
      )
    ) {
      return NextResponse.json(
        { message: "Checkout attempt is invalid. Please try again." },
        { status: 400 },
      );
    }
    const product = PRODUCTS[body.product];
    const pricingCountry = requestPricingCountry(request);
    const licensePrice = regionalPrice(body.product, pricingCountry);
    const orderId = `godfin_${body.checkoutAttemptId}`;
    const customerId = `gf_${createHmac("sha256", serverEnv.abuseHashSecret())
      .update(`cashfree-customer:${user.id}`)
      .digest("hex")
      .slice(0, 32)}`;
    const order = await createCashfreeOrder({
      orderId,
      amountMinor: licensePrice.amount,
      currency: licensePrice.currency,
      customerId,
      customerEmail: user.email,
      productName: product.description,
      tags: {
        product_code: product.code,
        user_id: user.id,
        pricing_country: licensePrice.country,
        pricing_version: licensePrice.priceVersion,
      },
    });
    if (!order.payment_session_id || order.order_id !== orderId) {
      throw new Error("Cashfree did not return a usable payment session.");
    }

    return NextResponse.json({
      paymentSessionId: order.payment_session_id,
      orderId,
      mode: cashfreeMode(),
    });
  } catch (error) {
    console.error("Checkout creation failed", error);
    return NextResponse.json(
      { message: "Secure checkout is temporarily unavailable." },
      { status: 500 },
    );
  }
}
