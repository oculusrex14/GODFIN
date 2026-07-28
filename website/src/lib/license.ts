import { createHash, createHmac } from "node:crypto";

export type LicenseTier = "pro" | "max";

function groups(value: string, size = 5): string[] {
  return value.match(new RegExp(`.{1,${size}}`, "g")) || [];
}

export function licenseKeyForSession(
  checkoutSessionId: string,
  tier: LicenseTier,
  signingSecret: string,
): string {
  const digest = createHmac("sha256", signingSecret)
    .update(`godfin-license:v1:${tier}:${checkoutSessionId}`)
    .digest("base64url")
    .replace(/[^A-Z0-9]/gi, "")
    .toUpperCase()
    .slice(0, 25);
  return `GODFIN-${tier.toUpperCase()}-${groups(digest).join("-")}`;
}

export function normalizeLicenseKey(value: string): string {
  return value.trim().toUpperCase().replace(/\s+/g, "");
}

export function hashLicenseKey(value: string): string {
  return createHash("sha256")
    .update(normalizeLicenseKey(value), "utf8")
    .digest("hex");
}

export function hashMachineId(value: string): string {
  return createHash("sha256")
    .update(`godfin-machine:v1:${value.trim()}`, "utf8")
    .digest("hex");
}
