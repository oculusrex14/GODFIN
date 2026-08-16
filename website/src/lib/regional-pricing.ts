import { ENTITLEMENTS, type PaidLicenseTier } from "@/lib/entitlements";
import type { ProductCode } from "@/lib/products";

export const PPP_PRICE_VERSION = "world-bank-icp-2021-v1";
export const DEFAULT_COUNTRY = "IN";
export const SUPPORTED_LICENSE_COUNTRIES = ["IN", "US"] as const;

export type LicenseCountry = (typeof SUPPORTED_LICENSE_COUNTRIES)[number];

export function normalizeLicenseCountry(value: unknown): LicenseCountry {
  if (
    typeof value === "string" &&
    SUPPORTED_LICENSE_COUNTRIES.includes(value.toUpperCase() as LicenseCountry)
  ) {
    return value.toUpperCase() as LicenseCountry;
  }
  return DEFAULT_COUNTRY;
}

/**
 * Resolve the checkout region from Vercel's server-populated country header.
 * Missing or unsupported signals use the higher US anchor whenever PPP is
 * enabled, so omitting a client hint can never unlock the India price.
 */
export function requestPricingCountry(request: Request): LicenseCountry {
  if (process.env.PPP_CHECKOUT_ENABLED !== "true") return "IN";
  const country = request.headers.get("x-vercel-ip-country")?.toUpperCase();
  return country === "IN" ? "IN" : "US";
}

export function isLicenseProduct(
  product: ProductCode,
): product is PaidLicenseTier {
  return product === "pro" || product === "max";
}

export function regionalPrice(
  product: ProductCode,
  countryValue: unknown,
  respectFeatureFlag = true,
): {
  country: LicenseCountry;
  currency: string;
  amount: number;
  priceVersion: string;
} {
  if (!isLicenseProduct(product)) {
    return {
      country: "IN",
      currency: "inr",
      amount: 0,
      priceVersion: PPP_PRICE_VERSION,
    };
  }

  const requestedCountry = normalizeLicenseCountry(countryValue);
  const pppEnabled =
    !respectFeatureFlag || process.env.PPP_CHECKOUT_ENABLED === "true";
  const country = pppEnabled ? requestedCountry : "IN";
  const configured = ENTITLEMENTS.tiers[product].price[country];
  return {
    country,
    currency: configured.currency,
    amount: configured.amount_minor,
    priceVersion: PPP_PRICE_VERSION,
  };
}

export function formattedLicensePrice(
  tier: PaidLicenseTier,
  country: LicenseCountry,
): string {
  const price = ENTITLEMENTS.tiers[tier].price[country];
  return new Intl.NumberFormat(country === "IN" ? "en-IN" : "en-US", {
    style: "currency",
    currency: price.currency.toUpperCase(),
    maximumFractionDigits: 0,
  }).format(price.amount_minor / 100);
}
