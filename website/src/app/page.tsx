import {
  ArrowRight,
  BadgeIndianRupee,
  Check,
  Database,
  FileArchive,
  FileChartColumn,
  FolderLock,
  HardDrive,
  Laptop,
  ListChecks,
  Repeat2,
  ShieldCheck,
  Sparkles,
  Target,
  WifiOff,
} from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { Suspense } from "react";

import { ProductDemoVideo } from "@/components/product-demo-video";
import { WaitlistForm } from "@/components/waitlist-form";
import { ENTITLEMENTS } from "@/lib/entitlements";
import { waitlistConfigured } from "@/lib/env";

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
    body: "Understand cash flow, recurring spend, budget pressure, and reviewed category trends without spreadsheet surgery.",
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

const productChapters = [
  {
    feature: "deterministic_classification",
    icon: ListChecks,
    eyebrow: "02 · Classification memory",
    title: "Correct it once. See why it was classified next time.",
    body: "Confirmed corrections build local merchant and transaction-pattern memory. GODFIN shows the source behind each choice, and finalized months remain untouched.",
    bullets: [
      "Exact merchant memory has priority",
      "Learning uses explicit corrections only",
      "Inspect, undo, export, or reset what was learned",
    ],
    image: "/screenshots/classification.png",
    alt: "GODFIN transaction list showing synthetic merchants, categories, and classification reasons",
  },
  {
    feature: "goal_contribution_ledger",
    icon: Target,
    eyebrow: "03 · Goals",
    title: "A savings goal with a history—not a mystery number.",
    body: "Start with what you have already saved, add deposits or withdrawals, and keep an auditable contribution ledger. Pro and Max can surface FD or RD candidates for confirmation.",
    bullets: [
      "Opening balance and future updates stay traceable",
      "Simulation discloses its formula, capacity, and data coverage",
      "Detected deposits never change a goal without confirmation",
    ],
    image: "/screenshots/goals.png",
    alt: "GODFIN goals screen with two synthetic goals, progress bars, and a deposit review indicator",
  },
  {
    feature: "recurring_detection",
    icon: Repeat2,
    eyebrow: "04 · Recurring review",
    title: "Recurring does not mean guessed.",
    body: "Calendar-aware detection looks for repeated evidence, amount variability, and merchant-account consistency. Review candidates before turning them into tracked subscriptions.",
    bullets: [
      "Monthly, quarterly, and annual patterns",
      "Transfers, reversals, and stale patterns are excluded",
      "Re-detect reports what was created, updated, or retired",
    ],
    image: "/screenshots/recurring.png",
    alt: "GODFIN subscriptions screen with synthetic recurring costs and a confirmation candidate",
  },
  {
    feature: "ca_tax_pack",
    icon: FileArchive,
    eyebrow: "05 · CA tax pack",
    title: "Hand over evidence, warnings, and filing context together.",
    body: "The paid CA export is one review-oriented ZIP: a multi-sheet XLSX, raw CSV, reconciliation JSON, manifest hashes, and an AY 2026–27 filing guide.",
    bullets: [
      "Flags unclassified, low-confidence, duplicate, and incomplete data",
      "Includes masked accounts and transfer/reversal review sheets",
      "Never claims transaction data alone is filing-ready",
    ],
    image: "/screenshots/ca-tax-pack.png",
    alt: "GODFIN reports screen showing the Export for CA tax-pack control and synthetic charts",
  },
  {
    feature: "local_sqlite",
    icon: HardDrive,
    eyebrow: "06 · Local boundary",
    title: "Your finance database stays on your computer.",
    body: "Statements, transaction history, category memory, goals, and reports remain on your computer. The website handles accounts, purchases, licenses, activations, and downloads.",
    bullets: [
      "No remote app database",
      "Local backups under your control",
      "AI is optional: local, bring-your-own provider, or none",
    ],
    image: "/screenshots/tutorial.png",
    alt: "GODFIN beginner tutorial explaining the app's local privacy boundary",
  },
];

for (const feature of [
  "manual_import",
  ...productChapters.map((chapter) => chapter.feature),
]) {
  if (ENTITLEMENTS.features[feature]?.status !== "released") {
    throw new Error(
      `Homepage product chapter references unreleased feature: ${feature}`,
    );
  }
}

export default function HomePage() {
  const waitlistEnabled = waitlistConfigured();
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
                Check private preview <ArrowRight size={17} />
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
              width={1244}
              height={716}
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
            <div className="eyebrow eyebrow-accent">
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

      <section className="section product-tour" id="product-tour">
        <div className="shell">
          <div className="section-head center">
            <div className="eyebrow eyebrow-accent">
              A complete local workflow
            </div>
            <h2>Follow the work, from statement to reviewed evidence.</h2>
            <p>
              Every demonstration below was captured from the working app with
              privacy-safe synthetic data. No generated UI art, hidden cloud
              ledger, or unshipped promise.
            </p>
          </div>

          <div className="product-chapters">
            <article className="product-chapter">
              <div className="product-copy">
                <div className="chapter-icon">
                  <Database size={20} />
                </div>
                <div className="eyebrow eyebrow-accent">
                  01 · Statement import
                </div>
                <h3>Review the bank file before it becomes your ledger.</h3>
                <p>
                  HDFC PDF and Excel imports preview, reconcile, and surface
                  exceptions before committing rows. OpenDataLoader remains
                  benchmark-only until it proves a material accuracy gain.
                </p>
                <ul className="chapter-list">
                  <li>Preview and reconcile before import</li>
                  <li>Duplicate and account-routing checks</li>
                  <li>Deterministic classification works without AI</li>
                </ul>
              </div>
              <figure className="product-demo">
                <ProductDemoVideo />
                <figcaption>
                  12-second capture from the seeded desktop app. Motion is
                  replaced with a still image when reduced motion is enabled.
                </figcaption>
              </figure>
            </article>

            {productChapters.map(
              (
                {
                  icon: Icon,
                  eyebrow,
                  title,
                  body,
                  bullets,
                  image,
                  alt,
                },
                index,
              ) => (
                <article
                  className={`product-chapter ${
                    index % 2 === 0 ? "product-chapter-reverse" : ""
                  }`}
                  key={title}
                >
                  <div className="product-copy">
                    <div className="chapter-icon">
                      <Icon size={20} />
                    </div>
                    <div className="eyebrow eyebrow-accent">
                      {eyebrow}
                    </div>
                    <h3>{title}</h3>
                    <p>{body}</p>
                    <ul className="chapter-list">
                      {bullets.map((bullet) => (
                        <li key={bullet}>{bullet}</li>
                      ))}
                    </ul>
                  </div>
                  <figure className="product-demo">
                    <Image src={image} width={1244} height={716} alt={alt} />
                    <figcaption>
                      Captured from the real app using synthetic data.
                    </figcaption>
                  </figure>
                </article>
              ),
            )}
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
              licenses, device activations, and downloads. Your app database remains on
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
                Account email, purchase records, license status, activations,
                and downloads. No transaction ledger.
              </p>
            </div>
          </div>
        </div>
      </section>

      <section className="section section-soft">
        <div className="shell">
          <div className="section-head center">
            <div className="eyebrow eyebrow-accent">
              Simple ownership
            </div>
            <h2>Start free. Upgrade once.</h2>
            <p>
              Core costs nothing. Pro and Max are lifetime desktop licenses.
              Neither plan includes hosted AI credits; use local AI, your own
              supported provider key, or no AI at all.
            </p>
          </div>
          <div className="inline-actions inline-actions-center">
            <Link className="button" href="/pricing">
              Compare plans <ArrowRight size={17} />
            </Link>
            <Link className="button-secondary" href="/docs">
              Read the setup guide
            </Link>
          </div>
        </div>
      </section>

      <section className="section" id="waitlist">
        <div className="shell waitlist-shell">
          <div className="section-head">
            <div className="eyebrow eyebrow-accent">
              Private launch
            </div>
            <h2>Help shape a finance app that starts with trust.</h2>
            <p>
              Join the double-opt-in waitlist for release updates. Tell us your
              operating system and intended use so we can prioritize real demand.
              Waitlist details never include desktop financial data.
            </p>
          </div>
          <Suspense fallback={<p className="lead">Loading waitlist form…</p>}>
            <WaitlistForm enabled={waitlistEnabled} />
          </Suspense>
        </div>
      </section>
    </>
  );
}
