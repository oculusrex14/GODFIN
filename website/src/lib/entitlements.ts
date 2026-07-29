import manifestJson from "@/generated/entitlements.json";

export type LicenseTier = "free" | "pro" | "max";
export type PaidLicenseTier = Exclude<LicenseTier, "free">;

type Manifest = {
  schema_version: number;
  included_hosted_ai_credits: number;
  tiers: Record<
    LicenseTier,
    {
      name: string;
      activation_limit: number;
      price: Record<string, { currency: string; amount_minor: number }>;
      released_features: string[];
    }
  >;
  features: Record<
    string,
    {
      status: "released" | "planned";
      label: string;
      description: string;
    }
  >;
};

export const ENTITLEMENTS = manifestJson as Manifest;

export function tierEntitlements(tier: LicenseTier) {
  return ENTITLEMENTS.tiers[tier];
}

export function releasedFeatures(tier: LicenseTier): string[] {
  return tierEntitlements(tier).released_features.filter(
    (code) => ENTITLEMENTS.features[code]?.status === "released",
  );
}

export function activationLimit(tier: PaidLicenseTier): number {
  return tierEntitlements(tier).activation_limit;
}
