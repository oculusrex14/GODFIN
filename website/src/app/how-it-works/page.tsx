import type { Metadata } from "next";
import { ArrowRight } from "lucide-react";
import Image from "next/image";
import Link from "next/link";

import { TrustStrip } from "@/components/trust-strip";
import { ENTITLEMENTS } from "@/lib/entitlements";

export const metadata: Metadata = {
  title: "See the real GODFIN workflow",
  description:
    "A plain-language tour through the real GODFIN desktop app, from a supported statement to a reviewed monthly picture.",
};

for (const feature of [
  "manual_import",
  "deterministic_classification",
  "recurring_detection",
  "goal_contribution_ledger",
  "basic_reports",
]) {
  if (ENTITLEMENTS.features[feature]?.status !== "released") {
    throw new Error(`How-it-works references unreleased feature: ${feature}`);
  }
}

const chapters = [
  {
    number: "01",
    title: "Check the file before it becomes your record",
    body: "Choose a supported statement in the desktop app. GODFIN shows what it recognized, the account and period, possible duplicates, and anything that needs attention before you reconcile it.",
    proof: [
      "Preview every row before importing",
      "Duplicate and account checks happen first",
      "Core sorting works without AI",
    ],
    image: "/screenshots/real-app/upload.png",
    alt: "Real GODFIN upload screen showing a synthetic statement ready for review",
  },
  {
    number: "02",
    title: "Fix it once. GODFIN remembers next time",
    body: "When a category looks wrong, correct it. Confirmed merchant memory can help with the next matching transaction, and GODFIN keeps the reason visible so the choice is never a mystery.",
    proof: [
      "Learns only from corrections you confirm",
      "Exact merchant memory has priority",
      "Inspect, undo, export, or reset what it learned",
    ],
    image: "/screenshots/real-app/review.png",
    alt: "Real GODFIN review queue showing synthetic transactions and category choices",
  },
  {
    number: "03",
    title: "Give a savings goal a history that adds up",
    body: "Start with what you have already saved, then record deposits or withdrawals. Pro and Max can suggest likely fixed- or recurring-deposit contributions, but a goal changes only after you confirm it.",
    proof: [
      "Starting balance and every update stay traceable",
      "Projections show their assumptions",
      "Detected deposits always wait for you",
    ],
    image: "/screenshots/real-app/budget.png",
    alt: "Real GODFIN budget and goals screen using synthetic amounts",
  },
  {
    number: "04",
    title: "Notice regular payments without filling the list with guesses",
    body: "GODFIN looks for the same merchant, a similar amount, and a meaningful rhythm. You review the result before it becomes a tracked regular payment.",
    proof: [
      "Looks for monthly, quarterly, and yearly rhythms",
      "Leaves out transfers and reversals",
      "Re-detect explains what changed",
    ],
    image: "/screenshots/real-app/subscriptions.png",
    alt: "Real GODFIN regular payments screen with made-up subscriptions",
  },
  {
    number: "05",
    title: "Answer normal questions about the month",
    body: "Bring money in, spending, regular payments, goals, budget pressure, and warnings into one clear report. Optional AI can help explain verified figures; it never calculates the authoritative totals.",
    proof: [
      "Monthly totals and category pressure at a glance",
      "Warnings stay attached to incomplete data",
      "Reports support review—they do not replace a CA",
    ],
    image: "/screenshots/real-app/reports.png",
    alt: "Real GODFIN reports screen showing a made-up household month",
  },
];

export default function HowItWorksPage() {
  return (
    <>
      <section className="how-hero">
        <div className="shell how-hero-grid">
          <div>
            <div className="eyebrow eyebrow-accent">The real desktop workflow</div>
            <h1>From a bank statement to a month that makes sense.</h1>
            <p>
              These are screens from the working GODFIN app—not a redrawn website
              mockup. The household and amounts are made up, but the tabs, layout,
              and features are the real product.
            </p>
            <div className="inline-actions">
              <Link className="button" href="/demo">Try the real app</Link>
              <Link className="button-secondary" href="/#waitlist">Join the early testers</Link>
            </div>
          </div>
          <div className="how-file-preview" aria-label="Example weekly GODFIN check-in">
            <div><span>Five-minute check-in</span><strong>A made-up July household</strong></div>
            <p><span>42</span> rows recognized</p>
            <p><span>3</span> need a quick review</p>
            <p><span>1</span> useful next step</p>
            <small>Nothing is added until you confirm.</small>
          </div>
        </div>
      </section>

      <section className="section product-tour">
        <div className="shell">
          <div className="section-head">
            <div className="eyebrow eyebrow-accent">Import → sort → review → understand</div>
            <h2>See the whole loop, screen by screen.</h2>
            <p>Each image comes from one privacy-safe demo build of the real desktop app.</p>
          </div>
          <div className="product-chapters">
            {chapters.map((chapter, index) => (
              <article
                className={`product-chapter${index % 2 ? " product-chapter-reverse" : ""}`}
                key={chapter.number}
              >
                <div className="product-copy">
                  <div className="eyebrow eyebrow-accent">{chapter.number}</div>
                  <h3>{chapter.title}</h3>
                  <p>{chapter.body}</p>
                  <ul className="chapter-list">
                    {chapter.proof.map((item) => <li key={item}>{item}</li>)}
                  </ul>
                </div>
                <figure className="product-demo">
                  <Image alt={chapter.alt} height={1080} sizes="(max-width: 900px) 100vw, 72vw" src={chapter.image} width={1920} />
                  <figcaption>Real GODFIN app · sample data · nothing here is connected to a bank</figcaption>
                </figure>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="section current-support" id="support">
        <div className="shell current-support-grid">
          <div><div className="eyebrow">Current beta focus</div><h2>Support grows only after the format is tested.</h2></div>
          <div>
            <p>Current verified repository evidence covers selected HDFC savings and credit-card formats, SBI savings relationship statements, and Kotak savings.</p>
            <p>The first builds focus on Apple Silicon Mac and Windows x64. Intel Mac and Linux distribution remain later work, so they are not advertised as current beta downloads.</p>
            <p>Bank files change over time. When a format is not recognized, GODFIN should say so instead of silently inventing rows.</p>
          </div>
        </div>
      </section>

      <TrustStrip compact />

      <section className="section how-final">
        <div className="shell">
          <h2>Try the same interface yourself.</h2>
          <p>The demo uses made-up data and makes no finance-service request.</p>
          <Link className="button" href="/demo">Open the real-app demo <ArrowRight size={17} /></Link>
        </div>
      </section>
    </>
  );
}
