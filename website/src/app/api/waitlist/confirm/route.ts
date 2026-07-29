import { createHash } from "node:crypto";
import { NextResponse } from "next/server";

import { siteUrl } from "@/lib/env";
import { createAdminClient } from "@/lib/supabase/admin";

export const runtime = "nodejs";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const token = url.searchParams.get("token") || "";
  if (!/^[A-Za-z0-9_-]{40,100}$/.test(token)) {
    return NextResponse.redirect(`${siteUrl()}/?waitlist=invalid#waitlist`);
  }

  try {
    const tokenHash = createHash("sha256").update(token).digest("hex");
    const admin = createAdminClient();
    const { data: entry, error } = await admin
      .from("waitlist_entries")
      .select("id,confirmed_at,confirmation_expires_at")
      .eq("confirmation_token_hash", tokenHash)
      .maybeSingle();
    if (error) throw error;
    if (!entry) {
      return NextResponse.redirect(`${siteUrl()}/?waitlist=invalid#waitlist`);
    }
    if (entry.confirmed_at) {
      return NextResponse.redirect(`${siteUrl()}/?waitlist=confirmed#waitlist`);
    }
    if (new Date(entry.confirmation_expires_at).getTime() < Date.now()) {
      return NextResponse.redirect(`${siteUrl()}/?waitlist=expired#waitlist`);
    }

    const { error: updateError } = await admin
      .from("waitlist_entries")
      .update({
        confirmed_at: new Date().toISOString(),
        confirmation_token_hash: createHash("sha256")
          .update(`used:${tokenHash}`)
          .digest("hex"),
        updated_at: new Date().toISOString(),
      })
      .eq("id", entry.id);
    if (updateError) throw updateError;

    return NextResponse.redirect(`${siteUrl()}/?waitlist=confirmed#waitlist`);
  } catch (error) {
    console.error("Waitlist confirmation failed", error);
    return NextResponse.redirect(`${siteUrl()}/?waitlist=error#waitlist`);
  }
}
