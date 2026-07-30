import type { Metadata } from "next";

import { SignInButton, SignOutButton } from "@/components/auth-controls";
import { CopyLicenseKey } from "@/components/copy-license-key";
import { CheckoutAnalytics } from "@/components/privacy-analytics";
import { DeviceActivations } from "@/components/device-activations";
import { ResendLicenseButton } from "@/components/resend-license-button";
import { serverEnv, supabasePublicConfig } from "@/lib/env";
import { licenseKeyForSession, type LicenseTier } from "@/lib/license";
import { isProductCode, PRODUCTS } from "@/lib/products";
import { stripe } from "@/lib/stripe";
import { createSupabaseServerClient } from "@/lib/supabase/server";

export const metadata: Metadata = {
  title: "Account",
  description: "Manage GODFIN licenses, AI credits, and downloads.",
};

export const dynamic = "force-dynamic";

type AccountSearchParams = Promise<{
  checkout?: string;
  next?: string;
  error?: string;
  session_id?: string;
}>;

export default async function AccountPage({
  searchParams,
}: {
  searchParams: AccountSearchParams;
}) {
  const params = await searchParams;
  const configured = Boolean(supabasePublicConfig());
  const supabase = await createSupabaseServerClient();
  const {
    data: { user },
  } = (await supabase?.auth.getUser()) || { data: { user: null } };

  let licenses: Array<{
    id: string;
    tier: string;
    key_last4: string;
    kind: "purchase" | "owner_test";
    status: string;
    issued_at: string;
  }> = [];
  let purchases: Array<{
    id: string;
    product_code: string;
    amount_total: number;
    currency: string;
    created_at: string;
  }> = [];
  let balance = 0;
  let activations: Array<{
    id: string;
    license_id: string;
    device_label: string | null;
    app_version: string | null;
    activated_at: string;
    last_seen_at: string;
  }> = [];
  let checkoutLicenseKey: string | null = null;
  let checkoutProductCode: string | null = null;

  if (supabase && user) {
    const [licenseResult, purchaseResult, creditResult, activationResult] = await Promise.all([
      supabase
        .from("licenses")
        .select("id,tier,key_last4,kind,status,issued_at")
        .order("issued_at", { ascending: false }),
      supabase
        .from("purchases")
        .select("id,product_code,amount_total,currency,created_at")
        .order("created_at", { ascending: false })
        .limit(20),
      supabase
        .from("credit_balances")
        .select("balance")
        .maybeSingle(),
      supabase
        .from("license_activations")
        .select("id,license_id,device_label,app_version,activated_at,last_seen_at")
        .is("deactivated_at", null)
        .order("last_seen_at", { ascending: false }),
    ]);
    licenses = licenseResult.data || [];
    purchases = purchaseResult.data || [];
    balance = creditResult.data?.balance || 0;
    activations = activationResult.data || [];

    if (
      params.checkout === "success" &&
      params.session_id?.startsWith("cs_")
    ) {
      try {
        const session = await stripe().checkout.sessions.retrieve(
          params.session_id.slice(0, 255),
        );
        const productCode = session.metadata?.product_code;
        if (
          session.payment_status === "paid" &&
          session.client_reference_id === user.id &&
          isProductCode(productCode)
        ) {
          checkoutProductCode = productCode;
          const tier = PRODUCTS[productCode].tier as LicenseTier | null;
          if (tier) {
            checkoutLicenseKey = licenseKeyForSession(
              session.id,
              tier,
              serverEnv.licenseSigningSecret(),
            );
          }
        }
      } catch (error) {
        console.error("Could not load checkout confirmation", error);
      }
    }
  }

  return (
    <>
      {checkoutProductCode ? (
        <CheckoutAnalytics
          product={checkoutProductCode}
          checkoutId={params.session_id || "unknown"}
        />
      ) : null}
      <section className="page-hero">
        <div className="shell">
          <div className="eyebrow" style={{ color: "var(--teal-dark)" }}>
            Website account
          </div>
          <h1>{user ? "Your GODFIN account" : "Licenses without a subscription"}</h1>
          <p>
            This account stores purchases, licenses, downloads, and AI credits.
            Your desktop transaction database is not synced here.
          </p>
        </div>
      </section>
      <section className="page-content">
        <div className="shell">
          {!configured ? (
            <div className="notice">
              Website authentication is ready for Supabase credentials. Add the
              production environment variables before launch.
            </div>
          ) : null}
          {params.checkout === "success" && !checkoutLicenseKey ? (
            <div className="notice">
              Payment received. License provisioning can take a few seconds;
              refresh if it has not appeared yet.
            </div>
          ) : null}
          {params.error ? (
            <div className="notice error-notice">
              Sign-in could not be completed. Please try again.
            </div>
          ) : null}

          {!user ? (
            <div className="account-card narrow">
              <h2>Sign in to continue</h2>
              <p className="lead">
                Google sign-in keeps checkout and license delivery tied to the
                correct email address.
              </p>
              <SignInButton next={params.next || "/account"} />
            </div>
          ) : (
            <>
              {checkoutLicenseKey ? (
                <CopyLicenseKey licenseKey={checkoutLicenseKey} />
              ) : null}
              <div className="inline-actions" style={{ marginBottom: 22 }}>
                <div>
                  <strong>{user.email}</strong>
                  <div style={{ color: "var(--muted)", fontSize: 13 }}>
                    AI top-up balance: {balance.toLocaleString("en-IN")} credits
                  </div>
                </div>
                <div style={{ marginLeft: "auto" }}>
                  <SignOutButton />
                </div>
              </div>
              <div className="account-grid">
                <section className="account-card">
                  <h2>Licenses</h2>
                  {licenses.length ? (
                    licenses.map((license) => (
                      <div key={license.id} style={{ marginTop: 20 }}>
                        <span className="status-pill">{license.status}</span>
                        {license.kind === "owner_test" ? (
                          <span
                            className="status-pill"
                            style={{ marginLeft: 8 }}
                          >
                            Owner test · no purchase
                          </span>
                        ) : null}
                        <h3 style={{ textTransform: "capitalize" }}>
                          GODFIN {license.tier}
                        </h3>
                        <p className="license-key">
                          GODFIN-{license.tier.toUpperCase()}-••••-••••-
                          {license.key_last4}
                        </p>
                        {license.kind === "purchase" ? (
                          <ResendLicenseButton licenseId={license.id} />
                        ) : (
                          <p style={{ color: "var(--muted)", fontSize: 13 }}>
                            Private test entitlement. Uses the same three-device
                            verification and deactivation controls as paid licenses.
                          </p>
                        )}
                      </div>
                    ))
                  ) : (
                    <p className="lead">No paid license is linked to this account.</p>
                  )}
                </section>
                <section className="account-card">
                  <h2>Purchase history</h2>
                  {purchases.length ? (
                    purchases.map((purchase) => (
                      <div
                        key={purchase.id}
                        style={{
                          borderTop: "1px solid var(--line)",
                          padding: "14px 0",
                        }}
                      >
                        <strong>{purchase.product_code.replaceAll("_", " ")}</strong>
                        <div style={{ color: "var(--muted)", fontSize: 13 }}>
                          ₹{(purchase.amount_total / 100).toLocaleString("en-IN")} ·{" "}
                          {new Date(purchase.created_at).toLocaleDateString("en-IN")}
                        </div>
                      </div>
                    ))
                  ) : (
                    <p className="lead">No purchases yet.</p>
                  )}
                </section>
              </div>
              <DeviceActivations
                activations={activations}
                licenseNames={Object.fromEntries(
                  licenses.map((license) => [
                    license.id,
                    `GODFIN ${license.tier.toUpperCase()}`,
                  ]),
                )}
              />
            </>
          )}
        </div>
      </section>
    </>
  );
}
