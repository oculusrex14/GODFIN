import { createHmac } from "node:crypto";
import { isIP } from "node:net";

import { NextResponse } from "next/server";

import { serverEnv } from "@/lib/env";
import { createAdminClient } from "@/lib/supabase/admin";

type LimitOptions = {
  bucket: string;
  limit: number;
  windowSeconds: number;
  subject?: string;
};

type RateLimitResult = {
  allowed: boolean;
  limit: number;
  remaining: number;
  retryAfter: number;
};

function requestAddress(request: Request): string {
  const candidate = (
    request.headers.get("x-vercel-forwarded-for")
    || request.headers.get("x-forwarded-for")
    || request.headers.get("x-real-ip")
    || ""
  )
    .split(",", 1)[0]
    .trim();
  return isIP(candidate) ? candidate : "unavailable";
}

function subjectHash(value: string): string {
  return createHmac("sha256", serverEnv.abuseHashSecret())
    .update(`godfin-public-limit:v1:${value}`)
    .digest("hex");
}

export async function checkRateLimit(
  request: Request,
  { bucket, limit, windowSeconds, subject }: LimitOptions,
): Promise<RateLimitResult> {
  const rawSubject = subject || `ip:${requestAddress(request)}`;
  const admin = createAdminClient();
  const { data, error } = await admin.rpc("check_public_rate_limit", {
    p_bucket: bucket,
    p_subject_hash: subjectHash(rawSubject),
    p_limit: limit,
    p_window_seconds: windowSeconds,
  });
  if (error) throw new Error("Public abuse control is unavailable.");
  const result = Array.isArray(data) ? data[0] : data;
  if (
    typeof result?.allowed !== "boolean"
    || !Number.isFinite(Number(result?.retry_after))
  ) {
    throw new Error("Public abuse control returned an invalid response.");
  }
  return {
    allowed: result.allowed,
    limit: Number(result.limit),
    remaining: Math.max(0, Number(result.remaining) || 0),
    retryAfter: Math.max(1, Math.ceil(Number(result.retry_after))),
  };
}

export function rateLimitResponse(
  result: RateLimitResult,
  message = "Too many attempts. Please wait and try again.",
) {
  return NextResponse.json(
    { message, retry_after: result.retryAfter },
    {
      status: 429,
      headers: {
        "Cache-Control": "no-store",
        "Retry-After": String(result.retryAfter),
        "X-RateLimit-Limit": String(result.limit),
        "X-RateLimit-Remaining": String(result.remaining),
      },
    },
  );
}
