import {
  ArrowRight,
  BadgeIndianRupee,
  Check,
  Database,
  FileChartColumn,
  FolderLock,
  Laptop,
  ShieldCheck,
  Sparkles,
  WifiOff,
} from "lucide-react";
import Image from "next/image";
import Link from "next/link";

const features = [
  {
    icon: FolderLock,
    title: "Your data stays yours",
    body: "Statements, transactions, categories, budgets, and reports live in SQLite on your laptop—not in a GODFIN cloud database.",
  },
  {
    icon: Sparkles,
    title: "Classification that learns",
    body: "Rules and merchant memory handle daily work locally. Optional AI helps only when you choose to enable it.",
  },
  {
    icon: FileChartColumn,
    title: "Reports built for India",
    body: "Understand cash flow, recurring spend, budget pressure, and financial-year exports without spreadsheet surgery.",
  },
  {
    icon: Database,
    title: "Bank-aware imports",
    body: "Import HDFC savings and credit-card statements today. The plugin architecture adds other banks only after their formats are verified.",
  },
  {
    icon: WifiOff,
    title: "Useful while offline",
    body: "The desktop app and its database run locally. Network access is optional for downloads, licensing, Gmail, or your chosen AI.",
  },
  {
    icon: BadgeIndianRupee,
    title: "Pay once",
    body: "Core is free forever. Pro and Max are one-time purchases—there is no software subscription waiting to compound.",
  },
];

export default function HomePage() {
  return (
    <>
      <section className="hero">
        <div className="shell hero-grid">
          <div>
            <div className="eyebrow">
              <span className="eyebrow-dot" />
              Local-first by design
            </div>
            <h1>The Finance App That Respects Your Privacy</h1>
            <p className="hero-copy">
              GODFIN runs on your laptop. Parse HDFC bank statements, classify
              spending, and generate useful reports without sending your
              financial life to someone else&apos;s database.
            </p>
            <div className="hero-actions">
              <Link className="button" href="/download">
                Download Free for macOS <ArrowRight size={17} />
              </Link>
              <Link className="button-ghost" href="/pricing">
                See pricing
              </Link>
            </div>
            <div className="trust-row" aria-label="Product principles">
              {[
                "Local SQLite",
                "No subscription",
                "No telemetry in the app",
                "Indian banks",
              ].map((item) => (
                <span className="trust-item" key={item}>
                  <Check size={13} color="#c9f36b" /> {item}
                </span>
              ))}
            </div>
          </div>
          <div className="app-frame">
            <Image
              src="/screenshots/dashboard.png"
              width={1365}
              height={768}
              priority
              alt="GODFIN desktop dashboard showing local financial summaries and charts"
            />
            <span className="app-frame-label">Captured from the real app</span>
          </div>
        </div>
      </section>

      <section className="section" id="features">
        <div className="shell">
          <div className="section-head">
            <div className="eyebrow" style={{ color: "var(--teal-dark)" }}>
              Built around your boundaries
            </div>
            <h2>Private enough for money. Practical enough for Monday.</h2>
            <p>
              GODFIN combines the control of a spreadsheet with the workflow of
              a modern finance app—without turning your transaction history into
              a hosted product.
            </p>
          </div>
          <div className="feature-grid">
            {features.map(({ icon: Icon, title, body }) => (
              <article className="feature-card" key={title}>
                <div className="feature-icon">
                  <Icon size={20} />
                </div>
                <h3>{title}</h3>
                <p>{body}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="section section-dark">
        <div className="shell">
          <div className="section-head center">
            <div className="eyebrow">
              <ShieldCheck size={14} /> Clear data boundary
            </div>
            <h2>The website sells the license. The app holds the money data.</h2>
            <p>
              Website accounts store only what is needed for purchases,
              licenses, downloads, and AI credits. Your app database remains on
              your device.
            </p>
          </div>
          <div className="privacy-diagram">
            <div className="privacy-node">
              <Laptop color="#c9f36b" />
              <strong>Your Mac or PC</strong>
              <p>
                Bank statements, transactions, merchant memory, budgets, audit
                history, reports, and your local PIN.
              </p>
            </div>
            <div className="privacy-arrow">→</div>
            <div className="privacy-node">
              <ShieldCheck color="#c9f36b" />
              <strong>GODFIN website</strong>
              <p>
                Account email, purchase records, license status, downloads, and
                optional credit balance. No transaction ledger.
              </p>
            </div>
          </div>
        </div>
      </section>

      <section className="section section-soft">
        <div className="shell">
          <div className="section-head center">
            <div className="eyebrow" style={{ color: "var(--teal-dark)" }}>
              Simple ownership
            </div>
            <h2>Start free. Upgrade once.</h2>
            <p>
              Core costs nothing. Pro and Max are lifetime desktop licenses.
              Credit packs are optional one-time top-ups.
            </p>
          </div>
          <div className="inline-actions" style={{ justifyContent: "center" }}>
            <Link className="button" href="/pricing">
              Compare plans <ArrowRight size={17} />
            </Link>
            <Link className="button-secondary" href="/docs">
              Read the setup guide
            </Link>
          </div>
        </div>
      </section>
    </>
  );
}
