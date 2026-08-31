import type { Metadata } from "next";
import Link from "next/link";

import { PublicDemo } from "@/components/public-demo";

export const metadata: Metadata = {
  title: "Public product demo",
  description: "Explore a made-up GODFIN household with no account, upload, or bank connection.",
};

export default function DemoPage() {
  return (
    <>
      <section className="demo-page-intro">
        <div className="shell demo-page-intro-row">
          <div>
            <div className="eyebrow eyebrow-accent">No sign-in. No upload.</div>
            <h1>Try GODFIN with a household that does not exist.</h1>
            <p>Explore current product ideas using one verified synthetic ledger. Nothing here is connected to a bank.</p>
          </div>
          <Link className="button" href="/#waitlist">Join the early-tester list <ArrowRightIcon /></Link>
        </div>
      </section>
      <section className="demo-page-canvas">
        <div className="shell"><PublicDemo /></div>
      </section>
    </>
  );
}

function ArrowRightIcon() {
  return <span aria-hidden="true">→</span>;
}
