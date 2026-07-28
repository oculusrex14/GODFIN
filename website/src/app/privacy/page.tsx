import type { Metadata } from "next";

import { AnalyticsPreferences } from "@/components/privacy-analytics";

export const metadata: Metadata = {
  title: "Privacy",
  description: "How GODFIN separates local financial data from website account data.",
};

export default function PrivacyPage() {
  return (
    <>
      <section className="page-hero">
        <div className="shell">
          <div className="eyebrow" style={{ color: "var(--teal-dark)" }}>
            Effective 28 July 2026
          </div>
          <h1>Privacy policy</h1>
          <p>
            The short version: your desktop financial database stays on your
            device. The website stores only the account and commerce data needed
            to sell and support GODFIN.
          </p>
        </div>
      </section>
      <section className="page-content legal">
        <article className="shell narrow prose">
          <h2>1. Two separate data boundaries</h2>
          <p>
            The GODFIN desktop application stores statements, transactions,
            balances, categories, budgets, merchant memory, reports, audit
            history, and local credentials in local storage controlled by you.
            We do not operate a remote transaction database for the app.
          </p>
          <p>
            The GODFIN website processes account identifiers, email address,
            purchase records, license status, device activation hashes, download
            access, and optional AI credit balances.
          </p>

          <h2>2. Website services</h2>
          <ul>
            <li>Vercel hosts the marketing and account website.</li>
            <li>Supabase provides website authentication and license records.</li>
            <li>Stripe processes payments; GODFIN does not store full card details.</li>
            <li>Resend delivers transactional license and account email.</li>
          </ul>

          <h2>3. Google sign-in and Gmail are different</h2>
          <p>
            Google sign-in on the website is used to authenticate your GODFIN
            website account. Optional Gmail access in the desktop app is a
            separate local integration for bank-alert ingestion. Website
            authentication does not grant the website access to your Gmail.
          </p>

          <h2>4. License verification</h2>
          <p>
            The app can send a license key, an anonymous device hash, app
            version, and verification timestamp to the website license API. The
            raw device identifier is not stored. Financial records are not part
            of this request.
          </p>

          <h2>5. Logs and security</h2>
          <p>
            Hosting and infrastructure providers may retain limited security,
            request, and error logs. We minimize application logging and do not
            intentionally place license keys, payment credentials, or desktop
            financial data in logs.
          </p>

          <h2>6. Optional website analytics</h2>
          <p>
            Anonymous Google Analytics is disabled until you explicitly allow
            it. When enabled, GODFIN requests IP anonymization and disables
            Google signals and advertising personalization. The desktop app
            does not send analytics, statements, transactions, balances, or
            categories.
          </p>
          <AnalyticsPreferences />

          <h2>7. Retention and deletion</h2>
          <p>
            Purchase and license records are retained as needed to provide your
            lifetime license, prevent fraud, and satisfy tax or legal duties.
            You may request deletion of optional account data, subject to records
            we must retain. Deleting the website account does not delete your
            local app database.
          </p>

          <h2>8. Your choices</h2>
          <p>
            Core requires no website account. Gmail, AI providers, embeddings,
            network access, and managed services are optional. You can export or
            delete local app data from the app.
          </p>

          <h2>9. Contact</h2>
          <p>
            Privacy requests can be sent to privacy@godfin.dev. Replace this
            address in your records if the production support address changes.
          </p>
        </article>
      </section>
    </>
  );
}
