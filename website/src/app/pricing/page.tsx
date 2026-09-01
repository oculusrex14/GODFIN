import type { Metadata } from "next";
import Link from "next/link";

import { ENTITLEMENTS } from "@/lib/entitlements";

export const metadata: Metadata = {
  title: "Planned lifetime pricing",
  description: "GODFIN Core is planned to stay free. Pro and Max are planned one-time desktop licenses.",
};

const plans = [
  {
    name: "Core",
    tagline: "For understanding one month at a time",
    price: "Free",
    suffix: "No payment",
    codes: ["manual_import", "deterministic_classification", "budgets", "goal_contribution_ledger", "recurring_detection", "basic_reports"],
    features: ["Import one supported statement at a time", "Understand and correct categories", "Track budgets and savings goals", "See regular payments and monthly reports", "Back up and export your own data"],
  },
  {
    name: "Pro",
    tagline: "For a fuller household picture",
    price: "₹4,999",
    suffix: "planned one-time India price",
    codes: ["multiple_accounts", "batch_statement_import", "generic_mapped_import", "gmail_sync", "advanced_reports", "advanced_recurring", "fd_rd_goal_detection"],
    features: ["Everything in Core", "More accounts and statement batches", "Guided CSV and spreadsheet mapping", "Optional read-only Gmail import", "Deeper reports and regular-payment review", "Suggestions when a fixed or recurring deposit may belong to a goal—GODFIN never moves the money"],
    featured: true,
  },
  {
    name: "Max",
    tagline: "For deeper reflection and reporting",
    price: "₹9,999",
    suffix: "planned one-time India price",
    codes: ["ai_classification", "ai_advisor", "personal_classifier", "net_worth", "behavior_insights", "ca_tax_pack"],
    features: ["Everything in Pro", "Review-oriented CA tax pack", "Net-worth tracking with visible freshness", "Plain-language money-behaviour reflections", "Optional AI explanations and classification help", "Use local AI or your own supported provider"],
  },
];

for (const plan of plans) {
  for (const code of plan.codes) {
    if (ENTITLEMENTS.features[code]?.status !== "released") {
      throw new Error(`Pricing references unreleased feature: ${code}`);
    }
  }
}

export default function PricingPage() {
  return (
    <>
      <section className="pricing-editorial-hero">
        <div className="shell">
          <div className="eyebrow eyebrow-accent">Planned public launch</div>
          <h1>Pay once. Keep it forever.</h1>
          <p>
            Start free. If GODFIN earns a place in your routine, Pro and Max are
            planned as one-time purchases—not another monthly bill. The beta is
            invitation-only and public checkout is closed, so this is not a request
            to pay today.
          </p>
        </div>
      </section>
      <section className="section">
        <div className="shell">
          <div className="pricing-grid pricing-grid-human">
            {plans.map((plan) => (
              <article className={`price-card${plan.featured ? " featured" : ""}`} key={plan.name}>
                {plan.featured ? <span className="price-badge">Most people</span> : null}
                <div className="eyebrow eyebrow-accent">{plan.name}</div>
                <p className="price-tagline">{plan.tagline}</p>
                <div className="price">{plan.price}</div>
                <p className="price-suffix">{plan.suffix}</p>
                <ul className="check-list">
                  {plan.features.map((feature) => <li key={feature}><span className="check">✓</span>{feature}</li>)}
                </ul>
              </article>
            ))}
          </div>
          <div className="pricing-single-action"><Link className="button" href="/#waitlist">Join the early testers</Link><span>No payment is taken during the beta.</span></div>
          <div className="pricing-clarity-grid">
            <article><strong>No subscription</strong><p>Pro and Max are planned as one-time desktop licenses.</p></article>
            <article><strong>No bundled AI usage</strong><p>The price never includes recurring hosted AI credits. Local AI and your own provider are separate choices.</p></article>
            <article><strong>Three active computers</strong><p>Paid licenses are planned for up to three active installations with account-based deactivation.</p></article>
          </div>
        </div>
      </section>
      <section className="section pricing-story-section">
        <div className="shell pricing-story-grid">
          <div>
            <div className="eyebrow eyebrow-accent">Why isn&apos;t all of it free?</div>
            <h2>Because independent software still takes real work.</h2>
          </div>
          <div>
            <p>
              GODFIN is built independently. Reliable statement import, safe local
              upgrades, support, signing, and accessibility all need time and paid
              services. Selling a useful product is the clearest way to fund that work
              without turning your finance history into the product.
            </p>
            <p>
              Core is planned to remain free for the basic monthly habit. A one-time
              Pro or Max license supports the deeper features and the work needed to
              keep the desktop app dependable.
            </p>
          </div>
        </div>
      </section>
      <section className="section section-soft">
        <div className="shell pricing-faq">
          <div className="section-head"><div className="eyebrow eyebrow-accent">Questions worth asking</div><h2>Before you choose a plan.</h2></div>
          <details><summary>Do I need AI to use GODFIN?</summary><p>No. Imports, rules, calculations, budgets, goals, and standard reports work without an AI model.</p></details>
          <details><summary>Can I buy a license during the beta?</summary><p>Not through the public website. A small selected cohort receives revocable test access without buying a permanent license.</p></details>
          <details><summary>Will prices be the same outside India?</summary><p>International launch prices will be set separately and shown clearly before checkout. The website will not ask you to interpret an internal pricing formula.</p></details>
          <details><summary>Does a license move my finance data online?</summary><p>No. Website accounts manage access and devices; ordinary desktop finance records stay on your computer.</p></details>
          <details><summary>Do I need a website account for Core?</summary><p>No. Once the desktop app is installed, Core can be set up and used without a GODFIN website account. The selected beta uses sign-in only to control private build access.</p></details>
          <details><summary>What does “lifetime” mean?</summary><p>It means the supported life of the purchased GODFIN product and major-version entitlement, not a promise that every future product, platform, or outside service is included forever.</p></details>
          <details><summary>Can I use or modify the source code?</summary><p>GODFIN uses PolyForm Noncommercial 1.0.0. Personal noncommercial use is permitted; commercial use and commercial forks require written approval.</p></details>
        </div>
      </section>
    </>
  );
}
