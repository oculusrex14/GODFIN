import {
  ArrowRight,
  Check,
  FileCheck2,
  HeartHandshake,
  Laptop,
  LockKeyhole,
  Sparkles,
} from "lucide-react";
import Link from "next/link";
import { Suspense } from "react";

import { ProductDemoVideo } from "@/components/product-demo-video";
import { WaitlistForm } from "@/components/waitlist-form";
import { ENTITLEMENTS } from "@/lib/entitlements";
import { waitlistConfigured } from "@/lib/env";

for (const feature of [
  "manual_import",
  "deterministic_classification",
  "goal_contribution_ledger",
  "recurring_detection",
  "basic_reports",
]) {
  if (ENTITLEMENTS.features[feature]?.status !== "released") {
    throw new Error(`Homepage references unreleased feature: ${feature}`);
  }
}

export default function HomePage() {
  const waitlistEnabled = waitlistConfigured();
  return (
    <>
      <section className="beta-hero">
        <div className="shell beta-hero-grid">
          <div className="beta-hero-copy">
            <div className="eyebrow eyebrow-accent">Early desktop beta</div>
            <h1>See your month. Keep the statement on your laptop.</h1>
            <p>
              Download a statement from your bank, open it in GODFIN on your laptop,
              and see where your money went. We never receive the file.
            </p>
            <div className="hero-actions">
              <Link className="button" href="/demo">Try the demo <ArrowRight size={17} /></Link>
              <Link className="button-secondary" href="/#waitlist">Join the early testers</Link>
            </div>
            <div className="beta-proof-row">
              <span><Check size={14} /> No account for the demo</span>
              <span><Check size={14} /> No software subscription planned</span>
              <span><Check size={14} /> Desktop first</span>
            </div>
          </div>
          <div className="golden-product-card" aria-label="Made-up July GODFIN summary">
            <div className="golden-product-top"><span>July 2026</span><small>Demo household</small></div>
            <div className="golden-product-balance"><span>Money left in July</span><strong>₹33,000</strong><small>after ₹11,000 of spending</small></div>
            <div className="golden-product-metrics"><article><span>Money in</span><strong>₹44,000</strong></article><article><span>Spent</span><strong>₹11,000</strong></article><article><span>Regular bills</span><strong>₹1,830</strong></article></div>
            <div className="golden-product-warning"><span>Try it yourself</span><strong>Open transactions, bills, a goal, and the report</strong></div>
            <p>Sample data · made-up household · not connected to a bank</p>
          </div>
        </div>
      </section>

      <section className="editorial-strip">
        <div className="shell editorial-strip-grid">
          <p>Built for the moment after you download a statement and think, “Where did my money go?”</p>
          <Link href="/how-it-works">See how it works <ArrowRight size={16} /></Link>
        </div>
      </section>

      <section className="section story-video-section">
        <div className="shell">
          <div className="section-head center">
            <div className="eyebrow eyebrow-accent">24 seconds, one sample month</div>
            <h2>See what GODFIN does before you join.</h2>
            <p>The video is silent and uses the same made-up household as the demo.</p>
          </div>
          <ProductDemoVideo />
        </div>
      </section>

      <section className="section beta-steps">
        <div className="shell">
          <div className="section-head">
            <div className="eyebrow eyebrow-accent">A simpler monthly habit</div>
            <h2>From bank file to a story you can use.</h2>
          </div>
          <div className="beta-step-grid">
            <article><span>01</span><FileCheck2 /><h3>Bring in a supported statement</h3><p>Preview what GODFIN found before rows become part of your month.</p></article>
            <article><span>02</span><Sparkles /><h3>Review the few things that need you</h3><p>See why something was classified, correct it, and let local memory help next time.</p></article>
            <article><span>03</span><HeartHandshake /><h3>Make one useful decision</h3><p>Check regular bills, move a goal forward, or take a clear report into a conversation.</p></article>
          </div>
        </div>
      </section>

      <section className="section beta-support">
        <div className="shell beta-support-grid">
          <div>
            <div className="eyebrow eyebrow-accent">Honest early support</div>
            <h2>Small enough to test properly.</h2>
            <p>
              The first tester builds focus on Mac computers with Apple chips and Windows PCs.
              Current verified statement formats include selected HDFC savings and
              credit-card statements, SBI savings relationship statements, and Kotak savings.
            </p>
            <Link className="text-link" href="/how-it-works#support">Read current limits →</Link>
          </div>
          <div className="support-pills" aria-label="Current beta focus">
            <span><Laptop /> Mac with Apple chip</span>
            <span><Laptop /> Windows PC</span>
            <span><FileCheck2 /> Selected HDFC formats</span>
            <span><FileCheck2 /> SBI savings relationship</span>
            <span><FileCheck2 /> Kotak savings</span>
          </div>
        </div>
      </section>

      <section className="section beta-boundary-section">
        <div className="shell beta-boundary-grid">
          <div className="boundary-mark"><LockKeyhole size={34} /><span>Local-first</span></div>
          <div>
            <div className="eyebrow">What stays private</div>
            <h2>Your statements and money records stay on your computer.</h2>
            <p>
              The desktop app keeps ordinary statements, transactions, categories,
              goals, and reports locally. The website handles the waitlist, selected
              beta access, licenses, and feedback only when you use those services.
            </p>
            <Link className="button-ghost" href="/privacy">Read the plain-language privacy page</Link>
          </div>
        </div>
      </section>

      <section className="section pricing-teaser">
        <div className="shell pricing-teaser-row">
          <div><div className="eyebrow eyebrow-accent">Planned launch pricing</div><h2>Free to begin. Pay once if you want more.</h2><p>Core is planned to remain free. Pro is ₹4,999 once and Max is ₹9,999 once in India. AI usage is not bundled into either license.</p></div>
          <Link className="button-secondary" href="/pricing">Compare the plans <ArrowRight size={16} /></Link>
        </div>
      </section>

      <section className="section waitlist-section" id="waitlist">
        <div className="shell waitlist-shell">
          <div className="section-head">
            <div className="eyebrow eyebrow-accent">Join the early testers</div>
            <h2>Try GODFIN early and tell us where it is confusing.</h2>
            <p>
              Tell us which computer you use and what you hope to understand better.
              We will confirm your email, then invite a small group. Never send
              a statement, account number, balance, PIN, key, or Gmail content.
            </p>
          </div>
          <Suspense fallback={<p className="lead">Loading the early-testers form…</p>}>
            <WaitlistForm enabled={waitlistEnabled} />
          </Suspense>
        </div>
      </section>
    </>
  );
}
