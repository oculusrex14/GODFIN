import type { Metadata } from "next";
import Link from "next/link";

import { WaitlistProfileForm } from "@/components/waitlist-profile-form";

export const metadata: Metadata = {
  title: "Waitlist confirmed",
  description: "Your GODFIN early-tester email is confirmed.",
  robots: { index: false, follow: false },
};

export default function WaitlistConfirmedPage() {
  return (
    <main className="page-content">
      <div className="shell narrow-shell">
        <div className="eyebrow eyebrow-accent">Email confirmed</div>
        <h1>You’re on the early-tester list.</h1>
        <p className="lead">
          The short profile below is optional. It helps us choose a useful mix of
          Apple Silicon Mac and Windows x64 testers without collecting financial data.
        </p>
        <WaitlistProfileForm />
        <p className="lead">
          Prefer to stop here? That is completely fine. You can also{" "}
          <Link className="text-link" href="/demo">try the made-up household demo</Link>.
        </p>
      </div>
    </main>
  );
}
