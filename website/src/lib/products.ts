export const PRODUCTS = {
  pro: {
    code: "pro",
    name: "GODFIN Pro",
    kind: "license",
    tier: "pro",
    amount: 499900,
    priceEnv: "STRIPE_PRICE_PRO",
    description: "GODFIN Pro lifetime desktop license",
    credits: 0,
  },
  max: {
    code: "max",
    name: "GODFIN Max",
    kind: "license",
    tier: "max",
    amount: 999900,
    priceEnv: "STRIPE_PRICE_MAX",
    description: "GODFIN Max lifetime desktop license",
    credits: 0,
  },
} as const;

export type ProductCode = keyof typeof PRODUCTS;

const RETIRED_HOSTED_CREDIT_CODES = new Set([
  "credits_starter",
  "credits_regular",
  "credits_power",
]);

export function isProductCode(value: unknown): value is ProductCode {
  return typeof value === "string" && value in PRODUCTS;
}

export function isRetiredHostedCreditCode(value: unknown): boolean {
  return typeof value === "string" && RETIRED_HOSTED_CREDIT_CODES.has(value);
}

export function stripePriceIdForEnvironment(envName: string): string {
  const value = process.env[envName]?.trim();
  if (!value) throw new Error(`Missing required environment variable: ${envName}`);
  return value;
}
