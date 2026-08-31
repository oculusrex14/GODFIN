import type { Metadata } from "next";

import { BetaInviteAccept } from "@/components/beta-invite-accept";

export const metadata: Metadata = {
  title: "Accept private beta invitation",
  description: "Bind a one-time GODFIN beta invitation to the invited Google account.",
  referrer: "no-referrer",
  robots: { index: false, follow: false },
};

export default function BetaAcceptPage() {
  return (
    <main className="page-content">
      <div className="shell narrow-shell">
        <div className="eyebrow eyebrow-accent">Selected testers only</div>
        <h1>Accept your GODFIN beta invitation.</h1>
        <p className="lead">
          The invitation is one-time, expires, and works only with the Google email
          address it was sent to.
        </p>
        <BetaInviteAccept />
      </div>
    </main>
  );
}
