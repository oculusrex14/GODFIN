import { createHash } from "node:crypto";
import { NextResponse } from "next/server";

import { checkRateLimit, rateLimitResponse } from "@/lib/abuse-control";
import { createAdminClient } from "@/lib/supabase/admin";

export const runtime = "nodejs";

export async function POST(request: Request) {
  try {
    const limit = await checkRateLimit(request, {
      bucket: "beta-invite-claim:address",
      limit: 20,
      windowSeconds: 60 * 60,
    });
    if (!limit.allowed) return rateLimitResponse(limit);
    const body = (await request.json()) as { token?: unknown };
    const token = typeof body.token === "string" ? body.token.trim() : "";
    if (!/^[A-Za-z0-9_-]{40,100}$/.test(token)) {
      return NextResponse.json({ message: "Invitation is invalid or expired." }, { status: 400 });
    }
    const tokenHash = createHash("sha256").update(token).digest("hex");
    const admin = createAdminClient();
    const { data: invite, error } = await admin
      .from("beta_invites")
      .select("id")
      .eq("token_hash", tokenHash)
      .is("used_at", null)
      .is("revoked_at", null)
      .gt("expires_at", new Date().toISOString())
      .maybeSingle();
    if (error) throw error;
    if (!invite) {
      return NextResponse.json({ message: "Invitation is invalid or expired." }, { status: 400 });
    }

    const response = NextResponse.json({ claimed: true });
    response.cookies.set("godfin_beta_invite", token, {
      httpOnly: true,
      sameSite: "lax",
      secure: process.env.NODE_ENV === "production",
      path: "/api/beta/invite",
      maxAge: 30 * 60,
    });
    return response;
  } catch (error) {
    console.error("Beta invite claim failed", {
      errorType: error instanceof Error ? error.name : "UnknownError",
    });
    return NextResponse.json({ message: "Invitation is temporarily unavailable." }, { status: 503 });
  }
}
