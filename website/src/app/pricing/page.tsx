import type { Metadata } from "next";
import Link from "next/link";

import { PurchaseButton } from "@/components/purchase-button";
import { ENTITLEMENTS } from "@/lib/entitlements";
import type { ProductCode } from "@/lib/products";
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
  const checkoutEnabled = process.env.CHECKOUT_ENABLED === "true";
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
                    Download free
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
                <PurchaseButton product={product} enabled={checkoutEnabled}>
                  Buy {name}
                </PurchaseButton>
              </article>
            ))}
          </div>
          <div className="callout">
            AI credits are not a subscription and are never bundled into a
            lifetime plan. Purchased top-ups remain available until used.
            Local AI and bring-your-own provider keys use no GODFIN credits.
          </div>
        </div>
      </section>
    </>
  );
}
