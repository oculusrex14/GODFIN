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
    price: "Free",
    suffix: "planned forever",
    codes: ["manual_import", "deterministic_classification", "budgets", "goal_contribution_ledger", "recurring_detection", "basic_reports"],
    features: ["Import one supported statement at a time", "Understand and correct categories", "Track budgets and savings goals", "See regular payments and monthly reports", "Back up and export your own data"],
  },
  {
    name: "Pro",
    price: "₹4,999",
    suffix: "planned one-time India price",
    codes: ["multiple_accounts", "batch_statement_import", "generic_mapped_import", "gmail_sync", "advanced_reports", "advanced_recurring", "fd_rd_goal_detection"],
    features: ["Everything in Core", "More accounts and statement batches", "Guided CSV and spreadsheet mapping", "Optional read-only Gmail import", "Deeper reports and regular-payment review", "FD and RD goal-contribution suggestions"],
    featured: true,
  },
  {
    name: "Max",
    price: "₹9,999",
    suffix: "planned one-time India price",
    codes: ["ai_classification", "ai_advisor", "personal_classifier", "net_worth", "behavior_insights", "ca_tax_pack"],
    features: ["Everything in Pro", "Optional AI explanations and classification help", "Net-worth tracking with visible freshness", "Plain-language money-behaviour reflections", "Review-oriented CA tax pack", "Use local AI or your own supported provider"],
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
          <h1>Software you can own, not another monthly bill.</h1>
          <p>
            The beta is invitation-only and public checkout is closed. These are the
            planned India launch prices—not a request to pay today.
          </p>
        </div>
      </section>
      <section className="section">
        <div className="shell">
          <div className="pricing-grid pricing-grid-human">
            {plans.map((plan) => (
              <article className={`price-card${plan.featured ? " featured" : ""}`} key={plan.name}>
                {plan.featured ? <span className="price-badge">A practical middle</span> : null}
                <div className="eyebrow eyebrow-accent">{plan.name}</div>
                <div className="price">{plan.price}</div>
                <p className="price-suffix">{plan.suffix}</p>
                <ul className="check-list">
                  {plan.features.map((feature) => <li key={feature}><span className="check">✓</span>{feature}</li>)}
                </ul>
                <Link className={plan.featured ? "button" : "button-secondary"} href="/#waitlist">
                  Join the beta waitlist
                </Link>
              </article>
            ))}
          </div>
          <div className="pricing-clarity-grid">
            <article><strong>No subscription</strong><p>Pro and Max are planned as one-time desktop licenses.</p></article>
            <article><strong>No bundled AI usage</strong><p>The price never includes recurring hosted AI credits. Local AI and your own provider are separate choices.</p></article>
            <article><strong>Three active computers</strong><p>Paid licenses are planned for up to three active installations with account-based deactivation.</p></article>
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
        </div>
      </section>
    </>
  );
}
