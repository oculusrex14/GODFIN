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
            <div className="status-pill">In development</div>
            <h2>v1.0 — Production foundation</h2>
            <p>
              Stable local encryption, expiring hashed sessions, per-IP PIN
              protection, safe statement imports, retained backups, health
              diagnostics, editable draft months, finalized-month locks,
              shareable transaction filters, and the first public website.
            </p>
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
