import type { Metadata } from "next";

import { publicContactConfig } from "@/lib/env";

export const metadata: Metadata = {
  title: "Terms",
  description: "Terms for GODFIN Core, Pro, and Max lifetime licenses.",
};

export default function TermsPage() {
  const { supportEmail } = publicContactConfig();
  return (
    <>
      <section className="page-hero">
        <div className="shell">
          <div className="eyebrow eyebrow-accent">
            Effective 29 July 2026
          </div>
          <h1>Terms of service</h1>
          <p>
            Plain-language operating terms for a local finance tool and its
            website services.
          </p>
        </div>
      </section>
      <section className="page-content legal">
        <article className="shell narrow prose">
          <h2>1. The product</h2>
          <p>
            GODFIN is personal finance software, not a bank, payment adviser,
            chartered accountant, investment adviser, or tax professional. Its
            classifications and reports can contain mistakes. You are
            responsible for reviewing financial decisions and official filings.
          </p>

          <h2>2. License</h2>
          <p>
            GODFIN source code is licensed under PolyForm Noncommercial 1.0.0.
            Personal, noncommercial use is permitted under that license.
            Commercial use, commercial redistribution, and forks intended for
            commercial use require prior written approval.
          </p>

          <h2>3. Core, Pro, and Max</h2>
          <p>
            Core is free. Pro and Max are one-time lifetime licenses for the
            major version and entitlement described at purchase. “Lifetime”
            refers to the supported life of the product, not the purchaser or
            any individual device. There is no recurring software fee.
          </p>

          <h2>4. Optional AI</h2>
          <p>
            Lifetime licenses include no hosted AI service or recurring AI
            allowance. GODFIN does not currently sell hosted AI credit packs.
            You may use supported local models or your own supported provider
            key, subject to that provider&apos;s terms and charges.
          </p>

          <h2>5. Payments and refunds</h2>
          <p>
            Payments are processed by Cashfree. Taxes, invoices, and supported
            methods depend on location and checkout. Except where applicable law
            requires otherwise, digital license refunds may be limited after a
            key has been activated.
            {supportEmail ? (
              <>
                {" "}
                Contact <a href={`mailto:${supportEmail}`}>{supportEmail}</a> for
                a good-faith review of billing mistakes or technical inability
                to use the product.
              </>
            ) : (
              <>
                {" "}
                Checkout remains disabled until a verified support address is
                configured for billing mistakes or technical inability to use
                the product.
              </>
            )}
          </p>

          <h2>6. Accounts and keys</h2>
          <p>
            Keep your website account and license key secure. You may not sell,
            publish, or share a key outside its three active installations.
            Devices can be reviewed and deactivated from the website account.
            We may suspend keys involved in fraud, chargebacks, abuse, or
            material violation of these terms.
          </p>

          <h2>7. Availability</h2>
          <p>
            The local app is designed to remain useful offline. Website
            licensing, downloads, email, and third-party integrations
            can experience downtime or provider changes. We will use reasonable
            care but do not promise uninterrupted service.
          </p>

          <h2>8. Warranty and liability</h2>
          <p>
            To the extent permitted by law, GODFIN is provided without implied
            warranties and is not liable for indirect or consequential loss.
            Our aggregate liability for a paid product is limited to the amount
            paid for that product, except where law does not allow that limit.
          </p>

          <h2>9. Changes and contact</h2>
          {supportEmail ? (
            <p>
              Material changes will be dated on this page. Product and billing
              questions can be sent to
              {" "}
              <a href={`mailto:${supportEmail}`}>{supportEmail}</a>.
            </p>
          ) : (
            <p>
              Material changes will be dated on this page. This private preview
              is not accepting payment because a verified public support
              address has not yet been configured.
            </p>
          )}
        </article>
      </section>
    </>
  );
}
