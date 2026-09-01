import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Contact and support",
  description: "How to contact GODFIN without sharing sensitive financial information.",
};

export default function ContactPage() {
  return (
    <>
      <section className="page-hero">
        <div className="shell">
          <div className="eyebrow eyebrow-accent">Contact and support</div>
          <h1>Tell us what went wrong—not what is in your bank account.</h1>
          <p>
            Email <a href="mailto:hello@godfin.dev">hello@godfin.dev</a> for beta,
            account, privacy, or future billing help. A useful report describes the
            screen, the action, and the error without attaching sensitive records.
          </p>
        </div>
      </section>
      <section className="page-content">
        <div className="shell feature-grid">
          <article className="content-card">
            <div className="eyebrow eyebrow-accent">Include</div>
            <h2>Enough detail to reproduce it</h2>
            <p>Your GODFIN version, computer type, the tab you were on, what you clicked, and the exact error text.</p>
          </article>
          <article className="content-card">
            <div className="eyebrow eyebrow-accent">Leave out</div>
            <h2>Sensitive financial information</h2>
            <p>Never email a raw statement, account or card number, balance, transaction list, PIN, license key, OAuth file, or AI key.</p>
          </article>
          <article className="content-card">
            <div className="eyebrow eyebrow-accent">Before writing</div>
            <h2>Check the beginner guide</h2>
            <p>The setup, imports, backups, licenses, Gmail, and AI sections answer the most common questions.</p>
            <Link className="text-link" href="/docs">Open the docs →</Link>
          </article>
        </div>
      </section>
    </>
  );
}
