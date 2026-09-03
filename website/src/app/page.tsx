import {
  ArrowRight,
  BookOpen,
  ChartPie,
  Check,
  FileCheck2,
  HeartHandshake,
  Laptop,
  LockKeyhole,
  RefreshCw,
  Sparkles,
  WalletCards,
} from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { Suspense } from "react";

import { ProductDemoVideo } from "@/components/product-demo-video";
import { TrustStrip } from "@/components/trust-strip";
import { WaitlistForm } from "@/components/waitlist-form";
import { ENTITLEMENTS } from "@/lib/entitlements";
import { waitlistConfigured } from "@/lib/env";

for (const feature of [
  "manual_import",
  "deterministic_classification",
  "goal_contribution_ledger",
  "recurring_detection",
  "basic_reports",
  "manual_transactions",
  "cash_flow",
  "behavior_insights",
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
            <div className="eyebrow eyebrow-accent">Local-first desktop beta</div>
            <h1>An AI-powered personal finance app for better money habits and decisions.</h1>
            <p>
              Track expenses, understand your choices, and build financial discipline
              with reliable local calculations and optional AI explanations. Core
              money tools continue to work without AI.
            </p>
            <div className="hero-actions">
              <Link className="button" href="/demo">Try the real app <ArrowRight size={17} /></Link>
              <Link className="text-link" href="/how-it-works">See how it works →</Link>
            </div>
            <p className="beta-availability-line">Selected beta: Apple Silicon Mac and Windows x64 · public downloads are not open yet</p>
            <div className="beta-proof-row">
              <span><Check size={14} /> No account for the demo</span>
              <span><Check size={14} /> No software subscription</span>
              <span><Check size={14} /> No AI needed for core calculations</span>
            </div>
          </div>
          <figure className="real-app-product-frame">
            <div className="real-app-window-bar" aria-hidden="true">
              <span /><span /><span />
              <small>GODFIN desktop</small>
            </div>
            <Image
              alt="The real GODFIN desktop dashboard showing a made-up July household with synthetic transactions"
              className="real-app-dashboard-image"
              height={1800}
              priority
              sizes="(max-width: 900px) 100vw, 56vw"
              src="/screenshots/real-app/godfin-dashboard-synthetic-2x.png"
              width={2880}
            />
            <figcaption>Actual GODFIN desktop interface · synthetic data · not connected to a bank</figcaption>
          </figure>
        </div>
      </section>

      <section className="section waitlist-section waitlist-section-priority" id="waitlist">
        <div className="shell waitlist-shell">
          <div className="section-head">
            <div className="eyebrow eyebrow-accent">Join the early testers</div>
            <h2>Help shape GODFIN before its first public release.</h2>
            <p>
              Tell us about your computer and what you want help understanding.
              We will confirm your email, then invite a focused group whose needs
              match the current beta.
            </p>
            <div className="beta-reward-card">
              <strong>A thank-you worth ₹9,999 at launch</strong>
              <span>
                Accepted testers who complete the feedback programme receive a
                complimentary lifetime Max license when GODFIN reaches its first
                public release. It is a license, not a subscription.
              </span>
            </div>
          </div>
          <Suspense fallback={<p className="lead">Loading the early-testers form…</p>}>
            <WaitlistForm enabled={waitlistEnabled} />
          </Suspense>
        </div>
      </section>

      <section className="founder-note-section">
        <div className="shell founder-note-grid">
          <div className="founder-mark" aria-hidden="true">GF</div>
          <blockquote>
            <p>
              “I built GODFIN because my income kept going up—and somehow my
              spending followed. I wanted a clearer answer than another spreadsheet,
              without handing a company my bank history.”
            </p>
            <footer><Link href="/about">Read why GODFIN exists →</Link><span>Built independently in India</span></footer>
          </blockquote>
        </div>
      </section>

      <section className="editorial-strip">
        <div className="shell editorial-strip-grid">
          <p>Built for the moment after you download a statement and think, “Where did my money go?”</p>
          <Link href="/how-it-works">See how it works <ArrowRight size={16} /></Link>
        </div>
      </section>

      <section className="section benefit-section">
        <div className="shell">
          <div className="section-head">
            <div className="eyebrow eyebrow-accent">What it changes for you</div>
            <h2>Money clarity, without giving up control.</h2>
            <p>Start with the outcome. The technical detail is there when you want it.</p>
          </div>
          <div className="benefit-grid">
            <article><LockKeyhole /><h3>Your records stay on your computer</h3><p>Statements, transactions, budgets, goals, and reports live in the desktop app—not a GODFIN transaction cloud.</p></article>
            <article><RefreshCw /><h3>It remembers your corrections</h3><p>Fix a category, inspect why it was chosen, and let confirmed merchant memory help next time.</p></article>
            <article><FileCheck2 /><h3>Classify transactions from Gmail alerts or bank statements</h3><p>Bring in supported Gmail transaction alerts or preview selected HDFC, SBI, and Kotak statement formats before any row becomes part of your month.</p></article>
            <article><WalletCards /><h3>Quick adds fill the gaps</h3><p>Add cash or a recent payment manually, then reconcile it when the official statement arrives.</p></article>
            <article><ChartPie /><h3>Reports answer normal questions</h3><p>See money in, spending, regular payments, goals, and category pressure without building a pivot table.</p></article>
            <article><BookOpen /><h3>Learn while you look</h3><p>Plain-language explanations sit beside calculations, while Max adds evidence-backed money-behaviour reflections.</p></article>
          </div>
        </div>
      </section>

      <section className="section story-video-section">
        <div className="shell">
          <div className="section-head center">
            <h2>See what GODFIN does before you join.</h2>
          </div>
          <ProductDemoVideo />
        </div>
      </section>

      <section className="section beta-steps">
        <div className="shell">
          <div className="section-head">
            <div className="eyebrow eyebrow-accent">A five-minute weekly check-in</div>
            <h2>From a bank file to one useful next step.</h2>
          </div>
          <div className="beta-step-grid">
            <article><span>01</span><FileCheck2 /><h3>Bring in what changed</h3><p>Preview a supported statement or quickly add a recent cash or card payment.</p></article>
            <article><span>02</span><Sparkles /><h3>Review only what needs you</h3><p>See why something was sorted, correct it, and keep the review queue small.</p></article>
            <article><span>03</span><HeartHandshake /><h3>Leave with one useful action</h3><p>Check a regular bill, move a goal forward, or read one evidence-backed insight.</p></article>
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
              Current verified formats include selected HDFC savings and credit-card
              statements, SBI savings relationship statements, and Kotak savings.
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

      <TrustStrip />

      <section className="section pricing-teaser">
        <div className="shell pricing-teaser-row">
          <div><div className="eyebrow eyebrow-accent">Built to stay independent</div><h2>Core features remain free. Paid users help fund the project.</h2><p>For people who want more, Pro is planned at ₹4,999 once and Max at ₹9,999 once in India. Neither lifetime license bundles recurring hosted AI usage.</p></div>
          <Link className="button-secondary" href="/pricing">Compare the plans <ArrowRight size={16} /></Link>
        </div>
      </section>
    </>
  );
}
