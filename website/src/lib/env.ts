function required(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value;
}

const PUBLIC_EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function present(name: string): boolean {
  return Boolean(process.env[name]?.trim());
}

function optionalPublicEmail(name: string): string | null {
  const value = process.env[name]?.trim();
  return value && PUBLIC_EMAIL_PATTERN.test(value) ? value : null;
}

export function siteUrl(): string {
  return (process.env.NEXT_PUBLIC_SITE_URL || "http://localhost:5300").replace(
    /\/$/,
    "",
  );
}

export function supabasePublicConfig() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL?.trim();
  const key = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY?.trim();
  return url && key ? { url, key } : null;
}

export function publicContactConfig() {
  const supportEmail = optionalPublicEmail("NEXT_PUBLIC_SUPPORT_EMAIL");
  const privacyEmail = optionalPublicEmail("NEXT_PUBLIC_PRIVACY_EMAIL");
  return {
    supportEmail,
    privacyEmail,
    commerceReady: Boolean(supportEmail && privacyEmail),
    waitlistReady: Boolean(privacyEmail),
  };
}

export function commerceConfigured(): boolean {
  const requiredCommerceEnvironment = [
    "NEXT_PUBLIC_SUPABASE_URL",
    "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY",
    "SUPABASE_SERVICE_ROLE_KEY",
    "ABUSE_HASH_SECRET",
    "STRIPE_SECRET_KEY",
    "STRIPE_WEBHOOK_SECRET",
    "STRIPE_PRICE_PRO",
    "STRIPE_PRICE_MAX",
    "LICENSE_SIGNING_SECRET",
    "LICENSE_ENTITLEMENT_ACTIVE_KEY_VERSION",
    "LICENSE_ENTITLEMENT_PRIVATE_KEYS_JSON",
    "RESEND_API_KEY",
    "RESEND_FROM_EMAIL",
  ];
  if (process.env.PPP_CHECKOUT_ENABLED === "true") {
    requiredCommerceEnvironment.push(
      "STRIPE_PRICE_PRO_US",
      "STRIPE_PRICE_MAX_US",
    );
  }
  return Boolean(
    process.env.CHECKOUT_ENABLED === "true"
      && publicContactConfig().commerceReady
      && requiredCommerceEnvironment.every(present),
  );
}

export function waitlistConfigured(): boolean {
  return Boolean(
    publicContactConfig().waitlistReady
      && [
        "NEXT_PUBLIC_SUPABASE_URL",
        "SUPABASE_SERVICE_ROLE_KEY",
        "ABUSE_HASH_SECRET",
        "RESEND_API_KEY",
        "RESEND_FROM_EMAIL",
      ].every(present),
  );
}

export const serverEnv = {
  required,
  supabaseServiceRoleKey: () => required("SUPABASE_SERVICE_ROLE_KEY"),
  abuseHashSecret: () => required("ABUSE_HASH_SECRET"),
  stripeSecretKey: () => required("STRIPE_SECRET_KEY"),
  stripeWebhookSecret: () => required("STRIPE_WEBHOOK_SECRET"),
  licenseSigningSecret: () => required("LICENSE_SIGNING_SECRET"),
  licenseEntitlementActiveKeyVersion: () =>
    required("LICENSE_ENTITLEMENT_ACTIVE_KEY_VERSION"),
  licenseEntitlementPrivateKeysJson: () =>
    required("LICENSE_ENTITLEMENT_PRIVATE_KEYS_JSON"),
  resendApiKey: () => required("RESEND_API_KEY"),
  resendFromEmail: () => required("RESEND_FROM_EMAIL"),
};
