import { createHash, randomBytes } from "node:crypto";
import { NextResponse } from "next/server";

import { checkRateLimit, rateLimitResponse } from "@/lib/abuse-control";
import { sendWaitlistConfirmedEmail } from "@/lib/email";
import { siteUrl } from "@/lib/env";
import { createAdminClient } from "@/lib/supabase/admin";

export const runtime = "nodejs";

export async function GET(request: Request) {
  try {
    const addressLimit = await checkRateLimit(request, {
      bucket: "waitlist-confirm:address",
      limit: 30,
      windowSeconds: 60 * 60,
    });
    if (!addressLimit.allowed) return rateLimitResponse(addressLimit);
  } catch (error) {
    console.error("Waitlist confirmation abuse control failed", error);
    return NextResponse.redirect(`${siteUrl()}/?waitlist=error#waitlist`);
  }
  const url = new URL(request.url);
  const token = url.searchParams.get("token") || "";
  if (!/^[A-Za-z0-9_-]{40,100}$/.test(token)) {
    return NextResponse.redirect(`${siteUrl()}/?waitlist=invalid#waitlist`);
  }

  try {
    const tokenHash = createHash("sha256").update(token).digest("hex");
    const profileToken = randomBytes(32).toString("base64url");
    const profileTokenHash = createHash("sha256")
      .update(profileToken)
      .digest("hex");
    const admin = createAdminClient();
    const { data: entry, error } = await admin
      .from("waitlist_entries")
      .update({
        confirmed_at: new Date().toISOString(),
        confirmation_token_hash: createHash("sha256")
          .update(`used:${tokenHash}`)
          .digest("hex"),
        profile_token_hash: profileTokenHash,
        profile_token_expires_at: new Date(
          Date.now() + 7 * 24 * 60 * 60 * 1000,
        ).toISOString(),
        updated_at: new Date().toISOString(),
      })
      .eq("confirmation_token_hash", tokenHash)
      .is("confirmed_at", null)
      .gt("confirmation_expires_at", new Date().toISOString())
      .select("id,email")
      .maybeSingle();
    if (error) throw error;
    if (!entry) {
      return NextResponse.redirect(`${siteUrl()}/?waitlist=invalid#waitlist`);
    }
    try {
      await sendWaitlistConfirmedEmail({
        to: entry.email,
        idempotencyKey: `waitlist-confirmed:${entry.id}`,
      });
    } catch (emailError) {
      console.error("Waitlist confirmation receipt could not be sent", {
        errorType: emailError instanceof Error ? emailError.name : "UnknownError",
      });
    }

    const response = NextResponse.redirect(`${siteUrl()}/waitlist/confirmed`);
    response.cookies.set("godfin_waitlist_profile", profileToken, {
      httpOnly: true,
      sameSite: "strict",
      secure: process.env.NODE_ENV === "production",
      path: "/api/waitlist/profile",
      maxAge: 7 * 24 * 60 * 60,
    });
    return response;
  } catch (error) {
    console.error("Waitlist confirmation failed", error);
    return NextResponse.redirect(`${siteUrl()}/?waitlist=error#waitlist`);
  }
}
