import { createHash } from "node:crypto";
import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { checkRateLimit, rateLimitResponse } from "@/lib/abuse-control";
import { normalizeEmail } from "@/lib/beta";
import { createAdminClient } from "@/lib/supabase/admin";
import { createSupabaseServerClient } from "@/lib/supabase/server";

export const runtime = "nodejs";

function clearInviteCookie(response: NextResponse) {
  response.cookies.set("godfin_beta_invite", "", {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/api/beta/invite",
    maxAge: 0,
  });
}

export async function POST(request: Request) {
  try {
    const limit = await checkRateLimit(request, {
      bucket: "beta-invite-accept:address",
      limit: 20,
      windowSeconds: 60 * 60,
    });
    if (!limit.allowed) return rateLimitResponse(limit);

    const supabase = await createSupabaseServerClient();
    const { data: { user } } = (await supabase?.auth.getUser()) || { data: { user: null } };
    const email = normalizeEmail(user?.email);
    if (!user || !email || !user.email_confirmed_at) {
      return NextResponse.json({ message: "Continue with the invited Google account." }, { status: 401 });
    }
    const cookieStore = await cookies();
    const token = cookieStore.get("godfin_beta_invite")?.value || "";
    if (!/^[A-Za-z0-9_-]{40,100}$/.test(token)) {
      return NextResponse.json({ message: "Open your fresh invitation link first." }, { status: 400 });
    }
    const admin = createAdminClient();
    const { data, error } = await admin.rpc("accept_beta_invite", {
      p_token_hash: createHash("sha256").update(token).digest("hex"),
      p_user_id: user.id,
      p_email: email,
    });
    if (error) throw error;
    const result = Array.isArray(data) ? data[0] : data;
    if (!result?.accepted) {
      const response = NextResponse.json(
        { message: "This invitation cannot be used with that account." },
        { status: 403 },
      );
      clearInviteCookie(response);
      return response;
    }
    const response = NextResponse.json({ accepted: true, phase: result.phase });
    clearInviteCookie(response);
    return response;
  } catch (error) {
    console.error("Beta invite acceptance failed", {
      errorType: error instanceof Error ? error.name : "UnknownError",
    });
    return NextResponse.json({ message: "Invitation is temporarily unavailable." }, { status: 503 });
  }
}
