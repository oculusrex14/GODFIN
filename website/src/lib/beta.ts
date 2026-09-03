import { createHmac } from "node:crypto";

export const BETA_PHASES = ["core", "pro", "max", "checkout_test"] as const;
export const BETA_STATUSES = [
  "shortlisted",
  "invited",
  "accepted",
  "active",
  "paused",
  "completed",
  "declined",
  "revoked",
] as const;

export type BetaPhase = (typeof BETA_PHASES)[number];
export type BetaStatus = (typeof BETA_STATUSES)[number];

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const COUNTRY_PATTERN = /^[A-Z]{2}$/;
const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function normalizeEmail(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const normalized = value.trim().toLowerCase().slice(0, 254);
  return EMAIL_PATTERN.test(normalized) ? normalized : null;
}

export function normalizeCountry(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const normalized = value.trim().toUpperCase();
  return COUNTRY_PATTERN.test(normalized) ? normalized : null;
}

export function inferredCountry(
  request: Request,
  localeCountry: unknown,
): { country: string | null; source: "vercel_geo" | "locale" | "unknown" } {
  const edgeCountry = normalizeCountry(request.headers.get("x-vercel-ip-country"));
  if (edgeCountry) return { country: edgeCountry, source: "vercel_geo" };
  const locale = normalizeCountry(localeCountry);
  if (locale) return { country: locale, source: "locale" };
  return { country: null, source: "unknown" };
}

export function cleanText(value: unknown, maximum: number): string {
  if (typeof value !== "string") return "";
  return value
    .replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/g, "")
    .replace(/\r\n?/g, "\n")
    .trim()
    .slice(0, maximum);
}

export function normalizeBankNames(value: unknown): string[] {
  const source = Array.isArray(value) ? value.join(",") : cleanText(value, 600);
  if (typeof source !== "string") return [];
  const unique = new Map<string, string>();
  for (const item of source.split(/[,;\n]/)) {
    const bank = cleanText(item, 80).replace(/\s+/g, " ");
    if (!bank) continue;
    const key = bank.toLocaleLowerCase("en-IN");
    if (!unique.has(key)) unique.set(key, bank);
    if (unique.size === 12) break;
  }
  return [...unique.values()];
}

export function containsSensitiveWaitlistProfile(value: string): boolean {
  return [
    /GODFIN-(?:PRO|MAX|BETA)-[A-Z0-9-]{12,}/i,
    /\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}/,
    /\b\d{6,19}\b/,
    /\b[A-Z]{4}0[A-Z0-9]{6}\b/,
    /\b[a-z0-9._-]{2,}@[a-z]{2,}\b/i,
    /\b(?:pin|password|passcode|cvv)\b\s*[:#=-]?\s*\d{3,}/i,
  ].some((pattern) => pattern.test(value));
}

export function safeAuthNext(value: unknown, fallback = "/account"): string {
  if (typeof value !== "string" || !value.startsWith("/") || value.startsWith("//")) {
    return fallback;
  }
  try {
    const parsed = new URL(value, "https://godfin.dev");
    if (parsed.origin !== "https://godfin.dev") return fallback;
    const allowed = new Set([
      "/account",
      "/beta",
      "/beta/accept",
      "/beta/feedback",
      "/download",
    ]);
    return allowed.has(parsed.pathname) && !parsed.search && !parsed.hash
      ? parsed.pathname
      : fallback;
  } catch {
    return fallback;
  }
}

export function betaLicenseKeyForTester(testerId: string, secret: string): string {
  if (!UUID_PATTERN.test(testerId) || secret.length < 24) {
    throw new Error("Beta license derivation input is invalid.");
  }
  const body = createHmac("sha256", secret)
    .update(`godfin-beta-license:v1:${testerId}`)
    .digest("hex")
    .toUpperCase();
  return `GODFIN-BETA-${body.slice(0, 8)}-${body.slice(8, 16)}-${body.slice(16, 24)}-${body.slice(24, 32)}`;
}

export function betaCheckoutEligibility(input: {
  status: string | null;
  phase: string | null;
  eligible: boolean;
}): boolean {
  return (
    input.status === "active" &&
    (input.phase === "max" || input.phase === "checkout_test") &&
    input.eligible
  );
}

export function containsSensitiveFeedback(value: string): boolean {
  return [
    /GODFIN-(?:PRO|MAX|BETA)-[A-Z0-9-]{12,}/i,
    /\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}/,
    /\b\d{12,19}\b/,
    /\b[A-Z]{4}0[A-Z0-9]{6}\b/,
    /\b[a-z0-9._-]{2,}@[a-z]{2,}\b/i,
  ].some((pattern) => pattern.test(value));
}
