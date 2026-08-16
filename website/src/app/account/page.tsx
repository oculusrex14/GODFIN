import type { Metadata } from "next";

import { SignInButton, SignOutButton } from "@/components/auth-controls";
import { CopyLicenseKey } from "@/components/copy-license-key";
import { CheckoutAnalytics } from "@/components/privacy-analytics";
import { DeviceActivations } from "@/components/device-activations";
import { ResendLicenseButton } from "@/components/resend-license-button";
import { serverEnv, supabasePublicConfig } from "@/lib/env";
import { licenseKeyForSession, type LicenseTier } from "@/lib/license";
import { isProductCode, PRODUCTS } from "@/lib/products";
import { createSupabaseServerClient } from "@/lib/supabase/server";

export const metadata: Metadata = {
  title: "Account",
  description: "Manage GODFIN licenses, device activations, and downloads.",
};

export const dynamic = "force-dynamic";

type AccountSearchParams = Promise<{
  checkout?: string;
  next?: string;
  error?: string;
  order_id?: string;
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
    status: string;
    license_id: string | null;
    payment_provider: string;
    provider_order_id: string | null;
    created_at: string;
  }> = [];
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
    const [licenseResult, purchaseResult, activationResult] = await Promise.all([
      supabase
        .from("licenses")
        .select("id,tier,key_last4,kind,status,issued_at")
        .order("issued_at", { ascending: false }),
      supabase
        .from("purchases")
        .select(
          "id,product_code,amount_total,currency,status,license_id,payment_provider,provider_order_id,created_at",
        )
        .order("created_at", { ascending: false })
        .limit(20),
      supabase
        .from("license_activations")
        .select("id,license_id,device_label,app_version,activated_at,last_seen_at")
        .is("deactivated_at", null)
        .order("last_seen_at", { ascending: false }),
    ]);
    licenses = licenseResult.data || [];
    purchases = purchaseResult.data || [];
    activations = activationResult.data || [];

    if (
      params.checkout === "return" &&
      params.order_id &&
      /^godfin_[0-9a-f-]{36}$/i.test(params.order_id)
    ) {
      const returnedPurchase = purchases.find(
        (purchase) =>
          purchase.payment_provider === "cashfree" &&
          purchase.provider_order_id === params.order_id,
      );
      if (
        returnedPurchase?.status === "paid" &&
        returnedPurchase.license_id &&
        isProductCode(returnedPurchase.product_code)
      ) {
        checkoutProductCode = returnedPurchase.product_code;
        const tier = PRODUCTS[returnedPurchase.product_code].tier as LicenseTier;
        checkoutLicenseKey = licenseKeyForSession(
          params.order_id,
          tier,
          serverEnv.licenseSigningSecret(),
        );
      }
    }
  }

  return (
    <>
      {checkoutProductCode ? (
        <CheckoutAnalytics
          product={checkoutProductCode}
          checkoutId={params.order_id || "unknown"}
        />
      ) : null}
      <section className="page-hero">
        <div className="shell">
          <div className="eyebrow eyebrow-accent">
            Website account
          </div>
          <h1>{user ? "Your GODFIN account" : "Licenses without a subscription"}</h1>
          <p>
            This account stores purchases, licenses, device activations, and
            downloads. Your desktop transaction database is not synced here.
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
          {params.checkout === "return" && !checkoutLicenseKey ? (
            <div className="notice">
              Cashfree is confirming the payment. License provisioning can take
              a few seconds; refresh if it has not appeared yet. GODFIN never
              activates a license from the browser return alone.
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
              <div className="inline-actions account-actions">
                <div>
                  <strong>{user.email}</strong>
                  <div className="account-caption">
                    Website account only · financial records stay in the desktop app
                  </div>
                </div>
                <div className="push-right">
                  <SignOutButton />
                </div>
              </div>
              <div className="account-grid">
                <section className="account-card">
                  <h2>Licenses</h2>
                  {licenses.length ? (
                    licenses.map((license) => (
                      <div className="license-entry" key={license.id}>
                        <span className="status-pill">{license.status}</span>
                        {license.kind === "owner_test" ? (
                          <span className="status-pill status-pill-offset">
                            Owner test · no purchase
                          </span>
                        ) : null}
                        <h3 className="text-capitalize">
                          GODFIN {license.tier}
                        </h3>
                        <p className="license-key">
                          GODFIN-{license.tier.toUpperCase()}-••••-••••-
                          {license.key_last4}
                        </p>
                        {license.kind === "purchase" ? (
                          <ResendLicenseButton licenseId={license.id} />
                        ) : (
                          <p className="account-caption">
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
                      <div className="purchase-entry" key={purchase.id}>
                        <strong>{purchase.product_code.replaceAll("_", " ")}</strong>
                        <div className="account-caption">
                          {new Intl.NumberFormat(
                            purchase.currency.toLowerCase() === "inr"
                              ? "en-IN"
                              : "en-US",
                            {
                              style: "currency",
                              currency: purchase.currency.toUpperCase(),
                            },
                          ).format(purchase.amount_total / 100)} · {purchase.status} ·{" "}
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
