import { NextResponse } from "next/server";

import { checkRateLimit, rateLimitResponse } from "@/lib/abuse-control";
import {
  activationLimit,
  ENTITLEMENTS,
  releasedFeatures,
  type PaidLicenseTier,
} from "@/lib/entitlements";
import { signEntitlement } from "@/lib/entitlement-signing";
import { hashLicenseKey, hashMachineId } from "@/lib/license";
import { createAdminClient } from "@/lib/supabase/admin";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  try {
    const body = (await request.json()) as {
      license_key?: unknown;
      machine_id?: unknown;
      device_label?: unknown;
      app_version?: unknown;
    };
    if (
      typeof body.license_key !== "string" ||
      body.license_key.length < 20 ||
      body.license_key.length > 120 ||
      typeof body.machine_id !== "string" ||
      body.machine_id.length < 8 ||
      body.machine_id.length > 300
    ) {
      return NextResponse.json(
        { valid: false, code: "INVALID_REQUEST", message: "License key or device ID is invalid." },
        { status: 400 },
      );
    }

    const addressLimit = await checkRateLimit(request, {
      bucket: "license-verify:address",
      limit: 120,
      windowSeconds: 60 * 60,
    });
    if (!addressLimit.allowed) return rateLimitResponse(addressLimit);

    const admin = createAdminClient();
    const deviceLabel =
      typeof body.device_label === "string"
        ? body.device_label.trim().slice(0, 80)
        : "GODFIN device";

    const licenseHash = hashLicenseKey(body.license_key);
    const licenseLimit = await checkRateLimit(request, {
      bucket: "license-verify:key",
      limit: 30,
      windowSeconds: 60 * 60,
      subject: `license:${licenseHash}`,
    });
    if (!licenseLimit.allowed) return rateLimitResponse(licenseLimit);
    const { data: license, error: licenseError } = await admin
      .from("licenses")
      .select("tier")
      .eq("key_hash", licenseHash)
      .maybeSingle();
    if (licenseError) throw licenseError;
    const tier = license?.tier as PaidLicenseTier | undefined;
    const limit = tier === "pro" || tier === "max" ? activationLimit(tier) : 3;

    const { data, error } = await admin.rpc("verify_license", {
      p_license_hash: licenseHash,
      p_machine_hash: hashMachineId(body.machine_id),
      p_device_label: deviceLabel,
      p_app_version:
        typeof body.app_version === "string" ? body.app_version.slice(0, 32) : null,
      p_activation_limit: limit,
    });
    if (error) throw error;

    const rawResult = Array.isArray(data) ? data[0] : data;
    const verifiedTier = rawResult?.tier as PaidLicenseTier | undefined;
    const result =
      rawResult?.valid && (verifiedTier === "pro" || verifiedTier === "max")
        ? {
            ...rawResult,
            features: releasedFeatures(verifiedTier),
            monthly_credits: ENTITLEMENTS.included_hosted_ai_credits,
            hosted_credits_included: ENTITLEMENTS.included_hosted_ai_credits,
            activation_limit: activationLimit(verifiedTier),
            entitlement: signEntitlement({
              licenseId: String(rawResult.license_id || ""),
              tier: verifiedTier,
              installationHash: hashMachineId(body.machine_id),
              licenseStateVersion: Number(rawResult.license_state_version),
            }),
          }
        : rawResult;
    const status = result?.valid ? 200 : 403;
    return NextResponse.json(
      result || {
        valid: false,
        code: "LICENSE_NOT_FOUND",
        message: "License key was not recognized.",
      },
      {
        status,
        headers: { "Cache-Control": "no-store" },
      },
    );
  } catch (error) {
    console.error("License verification failed", error);
    return NextResponse.json(
      {
        valid: false,
        code: "VERIFY_UNAVAILABLE",
        message: "License verification is temporarily unavailable.",
        retriable: true,
      },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }
}
