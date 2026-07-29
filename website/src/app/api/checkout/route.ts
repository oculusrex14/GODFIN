import { NextResponse } from "next/server";

import { siteUrl } from "@/lib/env";
import {
  isProductCode,
  PRODUCTS,
  stripePriceId,
  stripePriceIdForEnvironment,
} from "@/lib/products";
import { isLicenseProduct, regionalPrice } from "@/lib/regional-pricing";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { stripe } from "@/lib/stripe";

export const runtime = "nodejs";

export async function POST(request: Request) {
  try {
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

    const body = (await request.json()) as {
      product?: unknown;
      country?: unknown;
    };
    if (!isProductCode(body.product)) {
      return NextResponse.json({ message: "Unknown product." }, { status: 400 });
    }
    const product = PRODUCTS[body.product];
    const licensePrice = isLicenseProduct(body.product)
      ? regionalPrice(body.product, body.country)
      : null;
    const priceId = licensePrice
      ? stripePriceIdForEnvironment(licensePrice.priceEnv)
      : stripePriceId(body.product);

    const session = await stripe().checkout.sessions.create({
      mode: "payment",
      line_items: [{ price: priceId, quantity: 1 }],
      customer_email: user.email,
      customer_creation: "always",
      client_reference_id: user.id,
      billing_address_collection: "required",
      payment_intent_data: {
        description: product.description,
      },
      metadata: {
        product_code: product.code,
        user_id: user.id,
        pricing_country: licensePrice?.country || "IN",
        pricing_version: licensePrice?.priceVersion || "india-credit-packs-v1",
      },
      success_url: `${siteUrl()}/account?checkout=success&session_id={CHECKOUT_SESSION_ID}`,
      cancel_url: `${siteUrl()}/pricing?checkout=cancelled`,
    });

    return NextResponse.json({ url: session.url });
  } catch (error) {
    console.error("Checkout creation failed", error);
    return NextResponse.json(
      { message: "Secure checkout is temporarily unavailable." },
      { status: 500 },
    );
  }
}
