import { NextResponse } from "next/server";

import { checkRateLimit, rateLimitResponse } from "@/lib/abuse-control";
import { sendLicenseEmail } from "@/lib/email";
import { serverEnv } from "@/lib/env";
import { licenseKeyForSession, type LicenseTier } from "@/lib/license";
import { createAdminClient } from "@/lib/supabase/admin";
import { createSupabaseServerClient } from "@/lib/supabase/server";

export const runtime = "nodejs";

export async function POST(request: Request) {
  try {
    const addressLimit = await checkRateLimit(request, {
      bucket: "license-resend:address",
      limit: 15,
      windowSeconds: 24 * 60 * 60,
    });
    if (!addressLimit.allowed) return rateLimitResponse(addressLimit);
    const supabase = await createSupabaseServerClient();
    const {
      data: { user },
    } = (await supabase?.auth.getUser()) || { data: { user: null } };
    if (!user?.email) {
      return NextResponse.json({ message: "Sign in required." }, { status: 401 });
    }
    const userLimit = await checkRateLimit(request, {
      bucket: "license-resend:user",
      limit: 3,
      windowSeconds: 24 * 60 * 60,
      subject: `user:${user.id}`,
    });
    if (!userLimit.allowed) return rateLimitResponse(userLimit);

    const body = (await request.json()) as { license_id?: unknown };
    if (typeof body.license_id !== "string") {
      return NextResponse.json({ message: "Invalid license." }, { status: 400 });
    }

    const admin = createAdminClient();
    const { data: license } = await admin
      .from("licenses")
      .select("id,tier,user_id,kind")
      .eq("id", body.license_id)
      .eq("user_id", user.id)
      .maybeSingle();
    if (!license) {
      return NextResponse.json({ message: "License not found." }, { status: 404 });
    }
    if (license.kind === "owner_test") {
      return NextResponse.json(
        {
          message:
            "Owner-test licenses are installed directly and are not sent by email.",
        },
        { status: 409 },
      );
    }
    const { data: purchase } = await admin
      .from("purchases")
      .select("checkout_session_id")
      .eq("license_id", license.id)
      .maybeSingle();
    if (!purchase) {
      return NextResponse.json({ message: "Purchase not found." }, { status: 404 });
    }

    const tier = license.tier as LicenseTier;
    const key = licenseKeyForSession(
      purchase.checkout_session_id,
      tier,
      serverEnv.licenseSigningSecret(),
    );
    await sendLicenseEmail({
      to: user.email,
      licenseKey: key,
      tier,
      idempotencyKey: `resend:${license.id}:${new Date().toISOString().slice(0, 10)}`,
    });
    return NextResponse.json({ sent: true });
  } catch (error) {
    console.error("License resend failed", error);
    return NextResponse.json(
      { message: "License email could not be sent." },
      { status: 500 },
    );
  }
}
