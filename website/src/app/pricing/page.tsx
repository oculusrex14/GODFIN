import type { Metadata } from "next";
import Link from "next/link";

import { PurchaseButton } from "@/components/purchase-button";
import { ENTITLEMENTS } from "@/lib/entitlements";
import { commerceConfigured } from "@/lib/env";
import { formattedLicensePrice } from "@/lib/regional-pricing";

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
      ...ENTITLEMENTS.tiers.free.released_features.map(
        (code) => ENTITLEMENTS.features[code].label,
      ),
      "No account or telemetry required",
    ],
  },
  {
    name: "Pro",
    price: formattedLicensePrice("pro", "IN"),
    globalPrice: formattedLicensePrice("pro", "US"),
    suffix: "one time",
    featured: true,
    features: [
      "Everything released in Core",
      ...ENTITLEMENTS.tiers.pro.released_features
        .filter((code) => !ENTITLEMENTS.tiers.free.released_features.includes(code))
        .map((code) => ENTITLEMENTS.features[code].label),
      "Three active installations",
      "Zero recurring hosted AI credits",
    ],
  },
  {
    name: "Max",
    price: formattedLicensePrice("max", "IN"),
    globalPrice: formattedLicensePrice("max", "US"),
    suffix: "one time",
    features: [
      "Everything released in Pro",
      ...ENTITLEMENTS.tiers.max.released_features
        .filter((code) => !ENTITLEMENTS.tiers.pro.released_features.includes(code))
        .map((code) => ENTITLEMENTS.features[code].label),
      "Three active installations",
      "Zero recurring hosted AI credits",
    ],
  },
];

export default function PricingPage() {
  const checkoutEnabled = commerceConfigured();
  return (
    <>
      <section className="page-hero">
        <div className="shell">
          <div className="eyebrow eyebrow-accent">
            No software subscriptions
          </div>
          <h1>Own the app. Add AI only when it helps.</h1>
          <p>
            Core stays free. Pro and Max are lifetime desktop licenses. Private
            local AI and your own supported provider key are optional and are
            never bundled into the license price.
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
                {"globalPrice" in plan ? (
                  <p className="regional-anchor">
                    {plan.globalPrice} US anchor · regional checkout uses a
                    manually reviewed PPP table
                  </p>
                ) : null}
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
                    Check availability
                  </Link>
                ) : (
                  <PurchaseButton
                    product={plan.name === "Pro" ? "pro" : "max"}
                    secondary={plan.name === "Max"}
                    enabled={checkoutEnabled}
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
            <div className="eyebrow eyebrow-accent">
              Optional AI
            </div>
            <h2>Use AI without a GODFIN subscription.</h2>
            <p>
              GODFIN does not currently sell hosted AI credits. You can run a
              supported model privately on your computer, connect your own
              provider key, or continue without AI.
            </p>
          </div>
          <div className="callout">
            AI never determines authoritative totals. Imports, classification
            rules, budgets, calculations, and deterministic reports remain
            available without an LLM.
          </div>
        </div>
      </section>
    </>
  );
}
