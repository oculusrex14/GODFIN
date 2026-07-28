function required(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value;
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

export const serverEnv = {
  required,
  supabaseServiceRoleKey: () => required("SUPABASE_SERVICE_ROLE_KEY"),
  stripeSecretKey: () => required("STRIPE_SECRET_KEY"),
  stripeWebhookSecret: () => required("STRIPE_WEBHOOK_SECRET"),
  licenseSigningSecret: () => required("LICENSE_SIGNING_SECRET"),
  resendApiKey: () => required("RESEND_API_KEY"),
  resendFromEmail: () =>
    process.env.RESEND_FROM_EMAIL || "GODFIN <licenses@godfin.dev>",
};
