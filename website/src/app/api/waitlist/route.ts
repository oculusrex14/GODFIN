import { createHash, randomBytes } from "node:crypto";
import { NextResponse } from "next/server";

import { checkRateLimit, rateLimitResponse } from "@/lib/abuse-control";
import { sendWaitlistConfirmationEmail } from "@/lib/email";
import { siteUrl, waitlistConfigured } from "@/lib/env";
import { createAdminClient } from "@/lib/supabase/admin";

export const runtime = "nodejs";

const CONSENT_VERSION = "waitlist-2026-07-29-v1";
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const ALLOWED_OS = new Set(["macos", "windows", "linux", "other"]);

function safeAttribution(value: unknown): Record<string, string> {
  if (!value || typeof value !== "object") return {};
  const result: Record<string, string> = {};
  for (const key of ["source", "medium", "campaign", "content", "referrer"]) {
    const candidate = (value as Record<string, unknown>)[key];
    if (typeof candidate === "string" && candidate.trim()) {
      result[key] = candidate.trim().slice(0, 200);
    }
  }
  return result;
}

export async function POST(request: Request) {
  try {
    if (!waitlistConfigured()) {
      return NextResponse.json(
        {
          message:
            "The waitlist is closed until confirmation email and a privacy contact are configured.",
        },
        { status: 503 },
      );
    }
    const body = (await request.json()) as Record<string, unknown>;
    if (typeof body.company === "string" && body.company.trim()) {
      return NextResponse.json({ accepted: true }, { status: 202 });
    }
    const addressLimit = await checkRateLimit(request, {
      bucket: "waitlist:address",
      limit: 5,
      windowSeconds: 60 * 60,
    });
    if (!addressLimit.allowed) return rateLimitResponse(addressLimit);

    const email =
      typeof body.email === "string" ? body.email.trim().slice(0, 254) : "";
    const emailNormalized = email.toLowerCase();
    const country =
      typeof body.country === "string" ? body.country.trim().toUpperCase() : "";
    const os = typeof body.os === "string" ? body.os.trim().toLowerCase() : "";
    const intendedUse =
      typeof body.intended_use === "string"
        ? body.intended_use.trim().slice(0, 500)
        : "";
    const consented = body.consent === true;

    if (
      !EMAIL_PATTERN.test(email) ||
      !/^[A-Z]{2}$/.test(country) ||
      !ALLOWED_OS.has(os) ||
      intendedUse.length < 2 ||
      !consented
    ) {
      return NextResponse.json(
        { message: "Complete every field and confirm waitlist consent." },
        { status: 400 },
      );
    }

    const emailLimit = await checkRateLimit(request, {
      bucket: "waitlist:email",
      limit: 3,
      windowSeconds: 24 * 60 * 60,
      subject: `email:${emailNormalized}`,
    });
    if (!emailLimit.allowed) return rateLimitResponse(emailLimit);

    const admin = createAdminClient();
    const { data: existing, error: lookupError } = await admin
      .from("waitlist_entries")
      .select("id,confirmed_at")
      .eq("email_normalized", emailNormalized)
      .maybeSingle();
    if (lookupError) throw lookupError;
    if (existing?.confirmed_at) {
      return NextResponse.json({ accepted: true, confirmation_required: true });
    }

    const token = randomBytes(32).toString("base64url");
    const tokenHash = createHash("sha256").update(token).digest("hex");
    const expiresAt = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString();
    const payload = {
      email,
      email_normalized: emailNormalized,
      country,
      os,
      intended_use: intendedUse,
      consent_version: CONSENT_VERSION,
      attribution: safeAttribution(body.attribution),
      confirmation_token_hash: tokenHash,
      confirmation_expires_at: expiresAt,
      confirmation_sent_at: null,
      updated_at: new Date().toISOString(),
    };

    const { data: entry, error: upsertError } = await admin
      .from("waitlist_entries")
      .upsert(payload, { onConflict: "email_normalized" })
      .select("id")
      .single();
    if (upsertError) throw upsertError;

    const confirmationUrl = `${siteUrl()}/api/waitlist/confirm?token=${encodeURIComponent(token)}`;
    await sendWaitlistConfirmationEmail({
      to: email,
      confirmationUrl,
      idempotencyKey: `waitlist:${entry.id}:${tokenHash.slice(0, 12)}`,
    });
    await admin
      .from("waitlist_entries")
      .update({ confirmation_sent_at: new Date().toISOString() })
      .eq("id", entry.id);

    return NextResponse.json({ accepted: true, confirmation_required: true });
  } catch (error) {
    console.error("Waitlist signup failed", error);
    return NextResponse.json(
      { message: "Waitlist confirmation is temporarily unavailable." },
      { status: 503 },
    );
  }
}
