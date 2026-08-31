import type { Metadata } from "next";
import Link from "next/link";

import { WaitlistProfileForm } from "@/components/waitlist-profile-form";

export const metadata: Metadata = {
  title: "Waitlist confirmed",
  description: "Your email for the GODFIN early testers is confirmed.",
  robots: { index: false, follow: false },
};

export default function WaitlistConfirmedPage() {
  return (
    <main className="page-content">
      <div className="shell narrow-shell">
        <div className="eyebrow eyebrow-accent">Email confirmed</div>
        <h1>You’ve joined the early testers.</h1>
        <p className="lead">
          The short profile below is optional. It helps us choose a useful mix of
          Mac and Windows testers without collecting financial data.
        </p>
        <WaitlistProfileForm />
        <p className="lead">
          Prefer to stop here? That is completely fine. You can also{" "}
          <Link className="text-link" href="/demo">try the demo</Link>.
        </p>
      </div>
    </main>
  );
}
