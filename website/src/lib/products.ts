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
  credits_starter: {
    code: "credits_starter",
    name: "Starter credit pack",
    kind: "credits",
    tier: null,
    amount: 24900,
    priceEnv: "STRIPE_PRICE_CREDITS_STARTER",
    description: "500 GODFIN AI credits",
    credits: 500,
  },
  credits_regular: {
    code: "credits_regular",
    name: "Regular credit pack",
    kind: "credits",
    tier: null,
    amount: 49900,
    priceEnv: "STRIPE_PRICE_CREDITS_REGULAR",
    description: "1,200 GODFIN AI credits",
    credits: 1200,
  },
  credits_power: {
    code: "credits_power",
    name: "Power credit pack",
    kind: "credits",
    tier: null,
    amount: 99900,
    priceEnv: "STRIPE_PRICE_CREDITS_POWER",
    description: "3,000 GODFIN AI credits",
    credits: 3000,
  },
} as const;

export type ProductCode = keyof typeof PRODUCTS;

export function isProductCode(value: unknown): value is ProductCode {
  return typeof value === "string" && value in PRODUCTS;
}

export function stripePriceId(code: ProductCode): string {
  const envName = PRODUCTS[code].priceEnv;
  const value = process.env[envName]?.trim();
  if (!value) throw new Error(`Missing required environment variable: ${envName}`);
  return value;
}
