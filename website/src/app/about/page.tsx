import type { Metadata } from "next";
import { ArrowRight, BookOpen, HeartHandshake, IndianRupee, ShieldCheck } from "lucide-react";
import Image from "next/image";
import Link from "next/link";

import { TrustStrip } from "@/components/trust-strip";

export const metadata: Metadata = {
  title: "Why GODFIN exists",
  description:
    "The story behind an independent, local-first personal-finance app built in India.",
};

export default function AboutPage() {
  return (
    <>
      <section className="story-hero">
        <div className="shell story-hero-grid">
          <div>
            <div className="eyebrow eyebrow-accent">The story behind GODFIN</div>
            <h1>Why I built GODFIN</h1>
            <p>
              For a while, my income kept going up—and somehow my spending followed.
              I could see the balance, but I could not explain where the month went.
            </p>
          </div>
          <div className="builder-card">
            <Image alt="GODFIN vault-dial mark" height={112} src="/godfin-vault-dial.png" width={112} />
            <div>
              <strong>Built independently in India</strong>
              <span>A personal tool that grew into a product for people who wanted the same clarity.</span>
            </div>
          </div>
        </div>
      </section>

      <section className="section story-body">
        <div className="shell story-layout">
          <article className="story-prose">
            <p className="story-lead">My money did not make sense to me.</p>
            <p>
              Spreadsheets needed more discipline than I could give them every week.
              Many finance apps wanted a bank connection or a copy of my transaction
              history on somebody else&apos;s server. Neither felt like the right trade.
            </p>
            <p>
              So I started with a simpler idea: let a person bring in a statement,
              keep the record on their own computer, and turn it into a month they can
              actually understand. That personal tool became GODFIN.
            </p>
            <p>
              It is still being shaped with early testers. The aim is not to tell
              anyone what to do with their money. It is to make the facts clearer,
              explain the calculations, and leave the decision with the person who owns them.
            </p>
          </article>
          <aside className="story-principles" aria-label="GODFIN principles">
            <div><HeartHandshake /><strong>Understanding over tracking</strong><span>See patterns and pressure points, not just a list of payments.</span></div>
            <div><ShieldCheck /><strong>Privacy with clear boundaries</strong><span>Ordinary desktop finance records stay local; optional services are explained separately.</span></div>
            <div><BookOpen /><strong>Learning in context</strong><span>Plain-language explanations appear beside the ratios and calculations that need them.</span></div>
            <div><IndianRupee /><strong>A fair way to fund it</strong><span>Core is free; planned Pro and Max licenses are one-time purchases with no bundled AI usage.</span></div>
          </aside>
        </div>
      </section>

      <section className="section story-belief-section">
        <div className="shell story-belief-grid">
          <div>
            <div className="eyebrow eyebrow-accent">The product boundary</div>
            <h2>Your money is yours. So is the record of it.</h2>
          </div>
          <div>
            <p>
              GODFIN keeps ordinary statements, transactions, categories, budgets,
              goals, and reports inside the desktop app. Website accounts, selected
              beta access, licenses, and feedback are separate services.
            </p>
            <p>
              The repository stays private during the beta. The code is governed by
              PolyForm Noncommercial 1.0.0: personal noncommercial use is permitted,
              while commercial use and commercial forks require written approval.
            </p>
            <Link className="text-link" href="/privacy">Read the full privacy boundary →</Link>
          </div>
        </div>
      </section>

      <TrustStrip compact />

      <section className="section story-final">
        <div className="shell">
          <div className="eyebrow eyebrow-accent">Still being built with its users</div>
          <h2>This is the start, not a finished story.</h2>
          <p>
            The desktop beta is testing on Apple Silicon Macs and Windows PCs. Early
            feedback decides which rough edges get fixed and which banks come next.
          </p>
          <div className="inline-actions inline-actions-center">
            <Link className="button" href="/#waitlist">Join the early testers <ArrowRight size={17} /></Link>
            <Link className="text-link" href="/roadmap">See the roadmap →</Link>
          </div>
        </div>
      </section>
    </>
  );
}
