import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Changelog",
  description: "GODFIN desktop and website release notes.",
};

export default function ChangelogPage() {
  return (
    <>
      <section className="page-hero">
        <div className="shell">
          <div className="eyebrow eyebrow-accent">
            Release history
          </div>
          <h1>Changelog</h1>
          <p>Security and behavior changes, written for the people using them.</p>
        </div>
      </section>
      <section className="page-content">
        <div className="shell narrow">
          <article className="content-card prose">
            <div className="status-pill">Beta in progress</div>
            <h2>v1.0 — The first desktop beta</h2>
            <p>
              The first beta keeps money records protected on your computer, makes
              statement imports safer, keeps local backup copies, and lets you lock
              a finished month. The website now includes the sample-data demo and
              early-tester signup.
            </p>
            <details>
              <summary>Technical details for testers</summary>
              <p>Stable local encryption, expiring hashed sessions, per-IP PIN protection, reconciliation previews, retained backups, health diagnostics, editable draft months, finalized-month locks, and URL-backed transaction filters.</p>
            </details>
            <h3>Distribution</h3>
            <p>
              Signed desktop builds and automatic updates will appear here after
              packaging validation completes.
            </p>
          </article>
        </div>
      </section>
    </>
  );
}
