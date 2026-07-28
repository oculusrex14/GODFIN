import type { Metadata } from "next";
import Link from "next/link";

import { PurchaseButton } from "@/components/purchase-button";
import type { ProductCode } from "@/lib/products";

export const metadata: Metadata = {
  title: "Lifetime Pricing",
  description:
    "GODFIN Core is free. Pro and Max are one-time lifetime purchases with no software subscription.",
};

const plans = [
  {
    name: "Core",
    price: "Free",
    suffix: "forever",
    features: [
      "One HDFC account",
      "Manual statement upload",
      "Local rules + fuzzy classification",
      "Dashboard, budgets, and basic reports",
      "CSV export",
      "No account or telemetry required",
    ],
  },
  {
    name: "Pro",
    price: "₹4,999",
    suffix: "one time",
    featured: true,
    features: [
      "Everything in Core",
      "Multi-account transfer matching",
      "Verified bank parsers as they are released",
      "AI classification and advanced reports",
      "500 included AI credits each month",
      "Optional encrypted backup and sync",
      "Priority email support",
    ],
  },
  {
    name: "Max",
    price: "₹9,999",
    suffix: "one time",
    features: [
      "Everything in Pro",
      "2,500 included AI credits each month",
      "Up to five family profiles",
      "White-label reports",
      "Local REST API access",
      "Early parser access",
    ],
  },
];

const creditPacks: Array<{
  name: string;
  price: string;
  credits: string;
  product: ProductCode;
}> = [
  { name: "Starter", price: "₹249", credits: "500", product: "credits_starter" },
  { name: "Regular", price: "₹499", credits: "1,200", product: "credits_regular" },
  { name: "Power", price: "₹999", credits: "3,000", product: "credits_power" },
];

export default function PricingPage() {
  return (
    <>
      <section className="page-hero">
        <div className="shell">
          <div className="eyebrow" style={{ color: "var(--teal-dark)" }}>
            No software subscriptions
          </div>
          <h1>Own the app. Add AI only when it helps.</h1>
          <p>
            Core stays free. Pro and Max are lifetime desktop licenses. Optional
            credit packs are one-time purchases, and your own AI key bypasses
            GODFIN credits entirely.
          </p>
        </div>
      </section>
      <section className="section">
        <div className="shell">
          <div className="pricing-grid">
            {plans.map((plan) => (
              <article
                className={`price-card${plan.featured ? " featured" : ""}`}
                key={plan.name}
              >
                {plan.featured ? (
                  <span className="price-badge">Most popular</span>
                ) : null}
                <h2>{plan.name}</h2>
                <div className="price">
                  {plan.price} <small>{plan.suffix}</small>
                </div>
                <ul className="check-list">
                  {plan.features.map((feature) => (
                    <li key={feature}>
                      <span className="check">✓</span>
                      {feature}
                    </li>
                  ))}
                </ul>
                {plan.name === "Core" ? (
                  <Link className="button-secondary" href="/download">
                    Download free
                  </Link>
                ) : (
                  <PurchaseButton
                    product={plan.name === "Pro" ? "pro" : "max"}
                    secondary={plan.name === "Max"}
                  >
                    Get {plan.name} — {plan.price}
                  </PurchaseButton>
                )}
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="section section-soft">
        <div className="shell">
          <div className="section-head">
            <div className="eyebrow" style={{ color: "var(--teal-dark)" }}>
              Optional top-ups
            </div>
            <h2>AI credit packs</h2>
            <p>
              Credits cover hosted AI operations. Local rules, fuzzy matching,
              and your own provider key keep working without them.
            </p>
          </div>
          <div className="credit-grid">
            {creditPacks.map(({ name, price, credits, product }) => (
              <article className="credit-card" key={name}>
                <h3>{name}</h3>
                <strong>{credits} credits</strong>
                <p className="lead" style={{ fontSize: 14 }}>
                  {price} · one time
                </p>
                <PurchaseButton product={product}>
                  Buy {name}
                </PurchaseButton>
              </article>
            ))}
          </div>
          <div className="callout">
            AI credits are not a subscription. Included monthly allowances
            refresh by license tier; purchased top-ups remain available until
            used.
          </div>
        </div>
      </section>
    </>
  );
}
