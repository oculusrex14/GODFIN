import type { Metadata } from "next";
import Link from "next/link";

import { ENTITLEMENTS } from "@/lib/entitlements";

export const metadata: Metadata = {
  title: "How GODFIN works",
  description: "A plain-language tour from a supported statement to a reviewed monthly picture.",
};

for (const feature of ["manual_import", "deterministic_classification", "recurring_detection", "goal_contribution_ledger", "basic_reports"]) {
  if (ENTITLEMENTS.features[feature]?.status !== "released") throw new Error(`How-it-works references unreleased feature: ${feature}`);
}

const chapters = [
  { number: "01", title: "Preview the statement", body: "Choose a supported statement file in the desktop app. GODFIN shows what it recognized, the account and period, and anything that needs attention before you reconcile it.", note: "The public website does not accept statements." },
  { number: "02", title: "Review the month", body: "Transfers, refunds, reversals, and ordinary spending are kept separate. If a category looks wrong, correct it and inspect the reason behind future choices.", note: "A credit is not automatically called income." },
  { number: "03", title: "Notice what repeats", body: "See regular payments as review candidates, compare them with what you still use, and keep control over every change.", note: "GODFIN does not cancel a payment for you." },
  { number: "04", title: "Move a goal forward", body: "Start with what you have already saved, record deposits and withdrawals, and see a progress history that adds up.", note: "Detected FD or RD contributions require confirmation." },
  { number: "05", title: "Read the report", body: "Bring money in, spending, goals, regular bills, warnings, and optional explanations into one monthly story.", note: "Reports support review; they do not replace a CA or file a return." },
];

export default function HowItWorksPage() {
  return (
    <>
      <section className="how-hero">
        <div className="shell how-hero-grid">
          <div><div className="eyebrow eyebrow-accent">How it works</div><h1>A monthly routine without the spreadsheet maze.</h1><p>GODFIN helps you answer three questions: what happened, what needs attention, and what should I do next?</p><div className="inline-actions"><Link className="button" href="/demo">Try the demo</Link><Link className="button-secondary" href="/#waitlist">Join the early testers</Link></div></div>
          <div className="how-file-preview" aria-label="Example statement preview">
            <div><span>Statement preview</span><strong>HDFC Savings · July 2026</strong></div>
            <p><span>42</span> rows found</p>
            <p><span>3</span> need a quick review</p>
            <small>Nothing is added until you confirm.</small>
          </div>
        </div>
      </section>
      <section className="section how-chapters">
        <div className="shell">
          {chapters.map((chapter) => (
            <article key={chapter.number}>
              <span>{chapter.number}</span>
              <div><h2>{chapter.title}</h2><p>{chapter.body}</p><small>{chapter.note}</small></div>
            </article>
          ))}
        </div>
      </section>
      <section className="section current-support" id="support">
        <div className="shell current-support-grid">
          <div><div className="eyebrow">Current beta focus</div><h2>Support grows only after the format is tested.</h2></div>
          <div><p>Current verified repository evidence covers selected HDFC savings and credit-card formats, SBI savings relationship statements, and Kotak savings.</p><p>The first builds focus on Apple Silicon Mac and Windows x64. Intel Mac and Linux distribution remain later work, so they are not advertised as current beta downloads.</p><p>PDF formats vary between banks and over time. When a format is not recognized, GODFIN should say so instead of silently inventing rows.</p></div>
        </div>
      </section>
      <section className="section how-final"><div className="shell"><h2>Try it with a made-up household.</h2><p>The demo uses sample data and makes no network request for finance records.</p><Link className="button" href="/demo">Try the demo →</Link></div></section>
    </>
  );
}
