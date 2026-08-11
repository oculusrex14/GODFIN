import { NextResponse } from "next/server";

import { checkRateLimit } from "@/lib/abuse-control";
import { createSupabaseServerClient } from "@/lib/supabase/server";

export async function GET(request: Request) {
  const { origin, searchParams } = new URL(request.url);
  const code = searchParams.get("code");
  const requestedNext = searchParams.get("next") || "/account";
  const next = requestedNext.startsWith("/") ? requestedNext : "/account";

  try {
    const addressLimit = await checkRateLimit(request, {
      bucket: "auth-callback:address",
      limit: 60,
      windowSeconds: 60 * 60,
    });
    if (!addressLimit.allowed) {
      return NextResponse.redirect(`${origin}/account?error=rate-limit`);
    }
  } catch (error) {
    console.error("Authentication abuse control failed", error);
    return NextResponse.redirect(`${origin}/account?error=auth`);
  }

  if (code) {
    const supabase = await createSupabaseServerClient();
    const { error } = (await supabase?.auth.exchangeCodeForSession(code)) || {
      error: new Error("Supabase is not configured."),
    };
    if (!error) return NextResponse.redirect(`${origin}${next}`);
  }

  return NextResponse.redirect(`${origin}/account?error=auth`);
}
