import type { Metadata } from "next";
import Link from "next/link";

import { SignInButton } from "@/components/auth-controls";
import { BetaFeedbackForm } from "@/components/beta-feedback-form";
import { betaPortalState } from "@/lib/beta-access";
import { createSupabaseServerClient } from "@/lib/supabase/server";

export const metadata: Metadata = {
  title: "Beta feedback",
  description: "Share privacy-safe feedback about the GODFIN desktop beta.",
  robots: { index: false, follow: false },
};
export const dynamic = "force-dynamic";

export default async function BetaFeedbackPage() {
  const supabase = await createSupabaseServerClient();
  const { data: { user } } = (await supabase?.auth.getUser()) || { data: { user: null } };
  const tester = user ? await betaPortalState(user.id) : null;
  return (
    <main className="page-content">
      <div className="shell narrow-shell">
        <div className="eyebrow eyebrow-accent">Private beta feedback</div>
        <h1>Tell us what got in your way.</h1>
        <p className="lead">Short, specific descriptions are more useful than financial evidence. GODFIN does not accept attachments here.</p>
        {!user ? (
          <div className="account-card"><SignInButton next="/beta/feedback" /></div>
        ) : !tester || tester.status !== "active" ? (
          <div className="notice">Active beta access is required. <Link className="text-link" href="/beta">Check beta status</Link>.</div>
        ) : (
          <BetaFeedbackForm />
        )}
      </div>
    </main>
  );
}
