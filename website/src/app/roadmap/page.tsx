import type { Metadata } from "next";
import { ArrowRight } from "lucide-react";
import Link from "next/link";

import { TrustStrip } from "@/components/trust-strip";

export const metadata: Metadata = {
  title: "Roadmap",
  description: "What is live in the GODFIN beta, what is being improved, and what comes later.",
};

const milestones = [
  {
    period: "Now",
    status: "Live for selected testers",
    tone: "live",
    title: "Desktop beta on Mac and Windows",
    body: "Apple Silicon Mac and Windows x64 testers can use private builds with selected HDFC, SBI, and Kotak statement formats, local categorisation, goals, recurring review, reports, and optional advanced features.",
  },
  {
    period: "Through late 2026",
    status: "In progress",
    tone: "progress",
    title: "Make the desktop release dependable",
    body: "The focus is parser accuracy, migration safety, packaging, accessibility, performance, recovery, and the everyday experience reported by beta testers. New bank formats ship only after their exact files pass reconciliation tests.",
  },
  {
    period: "Target: January 2027",
    status: "Planned target",
    tone: "planned",
    title: "Desktop V1 public launch",
    body: "The target is a signed, updateable desktop release built from what the beta proves. This is a target rather than a guarantee; the date moves if safety or reliability still needs work.",
  },
  {
    period: "After desktop V1",
    status: "Exploring",
    tone: "exploring",
    title: "A smaller mobile companion",
    body: "Mobile is being explored for quick capture and useful check-ins. There is no public mobile beta date or cross-platform license promise yet, and the desktop privacy boundary remains the standard it must meet.",
  },
  {
    period: "Only when release-ready",
    status: "Controlled",
    tone: "controlled",
    title: "Broader distribution and source access",
    body: "The repository remains private during beta. Installers, update metadata, and any future source-access changes will be announced only after their own security, licensing, and launch reviews are complete.",
  },
];

export default function RoadmapPage() {
  return (
    <>
      <section className="roadmap-hero">
        <div className="shell">
          <div className="eyebrow eyebrow-accent">A public view of the work</div>
          <h1>The road ahead</h1>
          <p>
            Here is what is live, what is being tested, and what is still only a
            target. Dates can move as the beta reveals more; this page will move with them.
          </p>
        </div>
      </section>

      <section className="section roadmap-section">
        <div className="shell roadmap-layout">
          <aside>
            <div className="eyebrow eyebrow-accent">Current priority</div>
            <h2>Earn trust before adding reach.</h2>
            <p>
              Parser accuracy, local-data safety, signed packaging, and clear recovery
              matter more than a long feature list or an optimistic launch date.
            </p>
          </aside>
          <div className="roadmap-timeline">
            {milestones.map((milestone) => (
              <article key={milestone.title}>
                <div className={`roadmap-dot roadmap-dot-${milestone.tone}`} aria-hidden="true" />
                <div className="roadmap-meta"><span>{milestone.period}</span><strong>{milestone.status}</strong></div>
                <h2>{milestone.title}</h2>
                <p>{milestone.body}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="section roadmap-questions">
        <div className="shell">
          <div className="section-head"><div className="eyebrow eyebrow-accent">Where common requests stand</div><h2>What is—and is not—on the near-term list.</h2></div>
          <div className="roadmap-question-grid">
            <article><h3>More banks?</h3><p>Yes, carefully. A format is advertised only after representative files parse and reconcile reliably.</p></article>
            <article><h3>Windows?</h3><p>Already part of the selected desktop beta on Windows 10 22H2 and Windows 11 x64.</p></article>
            <article><h3>Automatic bank login?</h3><p>No current plan. GODFIN works from statement files and optional supported alerts instead of storing your bank credentials.</p></article>
            <article><h3>Cloud sync?</h3><p>Not on the current launch path. Any future option would need a separate privacy and security design and would never replace local storage by default.</p></article>
          </div>
        </div>
      </section>

      <TrustStrip compact />

      <section className="section roadmap-final">
        <div className="shell">
          <h2>Want to shape what reaches V1?</h2>
          <p>Early feedback carries more weight now than it will after launch.</p>
          <div className="inline-actions inline-actions-center">
            <Link className="button" href="/#waitlist">Join the early testers <ArrowRight size={17} /></Link>
            <Link className="text-link" href="/pricing">See planned pricing →</Link>
          </div>
        </div>
      </section>
    </>
  );
}
