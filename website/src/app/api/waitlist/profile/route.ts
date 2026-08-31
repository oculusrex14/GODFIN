import { createHash } from "node:crypto";
import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { checkRateLimit, rateLimitResponse } from "@/lib/abuse-control";
import { cleanText, containsSensitiveFeedback } from "@/lib/beta";
import { createAdminClient } from "@/lib/supabase/admin";

export const runtime = "nodejs";

const ALLOWED_BANKS = new Set(["hdfc", "sbi", "kotak", "other", "not_sure"]);
const ALLOWED_USES = new Set([
  "spending",
  "cash_flow",
  "recurring",
  "goals",
  "reports",
  "privacy",
]);
const PROFILE_CONSENT_VERSION = "beta-profile-2026-08-30-v1";

function selections(value: unknown, allowed: Set<string>): string[] {
  if (!Array.isArray(value)) return [];
  return [...new Set(value.filter((item): item is string => typeof item === "string"))]
    .map((item) => item.trim().toLowerCase())
    .filter((item) => allowed.has(item))
    .slice(0, 12);
}

export async function POST(request: Request) {
  try {
    const limit = await checkRateLimit(request, {
      bucket: "waitlist-profile:address",
      limit: 10,
      windowSeconds: 60 * 60,
    });
    if (!limit.allowed) return rateLimitResponse(limit);

    const cookieStore = await cookies();
    const token = cookieStore.get("godfin_waitlist_profile")?.value || "";
    if (!/^[A-Za-z0-9_-]{40,100}$/.test(token)) {
      return NextResponse.json(
        { message: "Open the fresh link from your confirmation email first." },
        { status: 401 },
      );
    }
    const tokenHash = createHash("sha256").update(token).digest("hex");
    const body = (await request.json()) as Record<string, unknown>;
    const platformDetail = cleanText(body.platform_detail, 160);
    const additionalContext = cleanText(body.additional_context, 1000);
    if (containsSensitiveFeedback(`${platformDetail}\n${additionalContext}`)) {
      return NextResponse.json(
        {
          message:
            "Remove account details, email addresses, long numbers, PINs, tokens, or license keys before continuing.",
        },
        { status: 400 },
      );
    }

    const admin = createAdminClient();
    const { data: entry, error: lookupError } = await admin
      .from("waitlist_entries")
      .select("id")
      .eq("profile_token_hash", tokenHash)
      .not("confirmed_at", "is", null)
      .gt("profile_token_expires_at", new Date().toISOString())
      .maybeSingle();
    if (lookupError) throw lookupError;
    if (!entry) {
      return NextResponse.json(
        { message: "That optional profile link is no longer valid." },
        { status: 401 },
      );
    }

    const { error: profileError } = await admin
      .from("beta_candidate_profiles")
      .upsert(
        {
          waitlist_entry_id: entry.id,
          banks: selections(body.banks, ALLOWED_BANKS),
          primary_use: selections(body.primary_use, ALLOWED_USES),
          gmail_test_interest: body.gmail_test_interest === true,
          feedback_commitment: body.feedback_commitment === true,
          platform_detail: platformDetail || null,
          additional_context: additionalContext || null,
          consent_version: PROFILE_CONSENT_VERSION,
          updated_at: new Date().toISOString(),
        },
        { onConflict: "waitlist_entry_id" },
      );
    if (profileError) throw profileError;
    const { error: updateError } = await admin
      .from("waitlist_entries")
      .update({
        profile_completed_at: new Date().toISOString(),
        profile_token_hash: null,
        profile_token_expires_at: null,
        updated_at: new Date().toISOString(),
      })
      .eq("id", entry.id)
      .eq("profile_token_hash", tokenHash);
    if (updateError) throw updateError;

    const response = NextResponse.json({ saved: true });
    response.cookies.set("godfin_waitlist_profile", "", {
      httpOnly: true,
      sameSite: "strict",
      secure: process.env.NODE_ENV === "production",
      path: "/api/waitlist/profile",
      maxAge: 0,
    });
    return response;
  } catch (error) {
    console.error("Waitlist profile submission failed", {
      errorType: error instanceof Error ? error.name : "UnknownError",
    });
    return NextResponse.json(
      { message: "The optional profile could not be saved right now." },
      { status: 503 },
    );
  }
}
