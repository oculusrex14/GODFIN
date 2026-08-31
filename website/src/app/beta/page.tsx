import type { Metadata } from "next";
import Link from "next/link";

import { SignInButton, SignOutButton } from "@/components/auth-controls";
import { BetaCheckoutButton } from "@/components/beta-checkout-button";
import { betaPortalState } from "@/lib/beta-access";
import { betaCheckoutConfigured } from "@/lib/env";
import { createSupabaseServerClient } from "@/lib/supabase/server";

export const metadata: Metadata = {
  title: "Private beta",
  description: "Your selected GODFIN beta access and testing phase.",
  robots: { index: false, follow: false },
};
export const dynamic = "force-dynamic";

type BetaSearchParams = Promise<{ checkout?: string; order_id?: string }>;

export default async function BetaPage({
  searchParams,
}: {
  searchParams: BetaSearchParams;
}) {
  const params = await searchParams;
  const supabase = await createSupabaseServerClient();
  const { data: { user } } = (await supabase?.auth.getUser()) || { data: { user: null } };
  const tester = user ? await betaPortalState(user.id) : null;

  return (
    <main>
      <section className="page-hero beta-page-hero">
        <div className="shell">
          <div className="eyebrow eyebrow-accent">Private desktop beta</div>
          <h1>{tester ? "Your GODFIN beta" : "Selected early testers"}</h1>
          <p>
            The first group focuses on Macs with Apple chips and Windows PCs. Financial
            data stays in the desktop app; this website stores access and feedback only.
          </p>
        </div>
      </section>
      <section className="page-content">
        <div className="shell narrow-shell">
          {!user ? (
            <div className="account-card">
              <h2>Sign in with your invited email</h2>
              <p className="lead">An account does not create beta access. Selection and a one-time invitation are required.</p>
              <SignInButton next="/beta" />
            </div>
          ) : !tester ? (
            <div className="account-card">
              <h2>No active invitation is linked to this account.</h2>
              <p className="lead">Join the early testers or accept the invite sent to your selected email address.</p>
              <div className="inline-actions">
                <Link className="button" href="/#waitlist">Join the early testers</Link>
                <SignOutButton />
              </div>
            </div>
          ) : (
            <>
              {params.checkout === "return" ? (
                <div className="notice" role="status">
                  {tester.checkoutCompletedAt
                    ? "Cashfree confirmed the private INR 1 checkout-flow test. No purchase or permanent license was created."
                    : "Cashfree is confirming the private checkout-flow test. Refresh this page in a moment if its status has not updated."}
                </div>
              ) : null}
              <div className="beta-status-grid">
                <section className="account-card">
                  <span className="status-pill">{tester.status}</span>
                  <h2>Phase: {tester.phase === "core" ? "Core" : tester.phase === "pro" ? "Pro" : tester.phase === "max" ? "Max" : "Checkout test"}</h2>
                  <p className="lead">Testing group {tester.cohort}</p>
                  {tester.status === "active" ? (
                    <p>Your access is active. Revocation never deletes your local GODFIN data.</p>
                  ) : tester.status === "paused" ? (
                    <p>This phase is paused. Your local data remains on your computer.</p>
                  ) : (
                    <p>This testing phase is {tester.status}.</p>
                  )}
                </section>
                <section className="account-card">
                  <h2>{tester.license ? `${tester.license.tier.toUpperCase()} beta entitlement` : "Core access"}</h2>
                  {tester.license ? (
                    <>
                      <p>Status: {tester.license.status} · key ending {tester.license.keyLast4}</p>
                      <p className="account-caption">Expires {tester.license.expiresAt ? new Date(tester.license.expiresAt).toLocaleDateString("en-IN") : "at the end of the beta"}. Uses the normal three-device limit.</p>
                      <Link className="text-link" href="/account">Manage devices and license</Link>
                    </>
                  ) : (
                    <p>Core stays license-free. Selection controls access to beta builds only.</p>
                  )}
                </section>
              </div>

              {tester.gmailTestRequired ? (
                <div className="notice">
                  Read-only Gmail testing: {tester.gmailTestAddedAt ? "your test-user access is marked ready" : "the owner still needs to add your email to Google’s test-user list"}. Website Google sign-in and desktop Gmail access are separate.
                </div>
              ) : null}

              {tester.checkoutEligible ? (
                <section className="account-card beta-checkout-card">
                  <h2>Checkout-flow test</h2>
                  <p>
                    You are allowlisted for a private INR 1 provider test. It does not
                    change public pricing or create a normal permanent purchase license.
                  </p>
                  <p className="account-caption">
                    {betaCheckoutConfigured()
                      ? "The sandbox gate is available for the selected test run."
                      : "The owner-controlled checkout gate is currently off."}
                  </p>
                  {!tester.checkoutCompletedAt ? (
                    <BetaCheckoutButton enabled={betaCheckoutConfigured()} />
                  ) : (
                    <p className="notice">This selected checkout-flow test is complete.</p>
                  )}
                </section>
              ) : null}

              <div className="inline-actions beta-actions">
                {tester.status === "active" ? <Link className="button" href="/download">Open beta downloads</Link> : null}
                <Link className="button-secondary" href="/beta/feedback">Share feedback</Link>
                <SignOutButton />
              </div>
            </>
          )}
        </div>
      </section>
    </main>
  );
}
