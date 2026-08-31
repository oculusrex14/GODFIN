"use client";

import {
  ArrowLeft,
  ArrowRight,
  BarChart3,
  CalendarClock,
  CheckCircle2,
  LayoutDashboard,
  LockKeyhole,
  Search,
  Target,
  WalletCards,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import demo from "../../public/demo/demo-data.json";

type DemoView = "overview" | "transactions" | "bills" | "goal" | "report" | "privacy";
type DemoMode = "welcome" | "tour" | "explore";

const views: Array<{ id: DemoView; label: string; icon: typeof LayoutDashboard }> = [
  { id: "overview", label: "Overview", icon: LayoutDashboard },
  { id: "transactions", label: "Transactions", icon: WalletCards },
  { id: "bills", label: "Regular bills", icon: CalendarClock },
  { id: "goal", label: "Savings goal", icon: Target },
  { id: "report", label: "Monthly report", icon: BarChart3 },
  { id: "privacy", label: "Privacy", icon: LockKeyhole },
];

const tourSteps: Array<{ view: DemoView; title: string; body: string }> = [
  { view: "overview", title: "Start with the month", body: "See what came in, what went out, and what was left—without treating every credit as income." },
  { view: "transactions", title: "Keep the reasoning visible", body: "Open any row to see why it belongs in a category or why a transfer is excluded from spending." },
  { view: "bills", title: "Spot regular commitments", body: "Two made-up subscriptions add up to ₹1,830 a month. Nothing is cancelled or changed without you." },
  { view: "goal", title: "Track real progress", body: "The goal keeps its deposit and withdrawal history, so ₹8,000 is explainable rather than a mystery total." },
  { view: "report", title: "Finish with a useful story", body: "The report brings monthly totals, net worth, and review warnings together. It does not pretend to be tax advice." },
  { view: "privacy", title: "Know the boundary", body: "The public demo is made-up and disconnected. In the desktop app, ordinary finance records stay on the computer." },
];

function money(value: string) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(Number(value));
}

export function PublicDemo() {
  const [mode, setMode] = useState<DemoMode>("welcome");
  const [view, setView] = useState<DemoView>("overview");
  const [tourIndex, setTourIndex] = useState(0);
  const [search, setSearch] = useState("");
  const [reasonId, setReasonId] = useState<string | null>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);

  const filteredTransactions = useMemo(() => {
    const query = search.trim().toLowerCase();
    return query
      ? demo.transactions.filter((row) =>
          `${row.merchant} ${row.category}`.toLowerCase().includes(query),
        )
      : demo.transactions;
  }, [search]);

  function beginTour() {
    setMode("tour");
    setTourIndex(0);
    setView(tourSteps[0].view);
  }

  const moveTour = useCallback((direction: -1 | 1) => {
    const next = tourIndex + direction;
    if (next < 0) return;
    if (next >= tourSteps.length) {
      setMode("explore");
      setView("overview");
      return;
    }
    setTourIndex(next);
    setView(tourSteps[next].view);
  }, [tourIndex]);

  useEffect(() => {
    headingRef.current?.focus();
  }, [view, mode]);

  useEffect(() => {
    if (mode !== "tour") return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "ArrowRight") moveTour(1);
      if (event.key === "ArrowLeft") moveTour(-1);
      if (event.key === "Escape") setMode("explore");
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [mode, moveTour]);

  return (
    <div className="public-demo" data-demo-runtime="static">
      <div className="demo-disclosure" role="note">
        <span className="demo-disclosure-dot" />
        {demo.disclosure}
      </div>

      {mode === "welcome" ? (
        <section className="demo-welcome" aria-labelledby="demo-welcome-title">
          <div className="demo-welcome-copy">
            <div className="eyebrow eyebrow-accent">Try the workflow</div>
            <h2 id="demo-welcome-title">A made-up month you can safely explore.</h2>
            <p>
              No account, upload, bank connection, or AI is used here. Take the short
              guided tour, or look around at your own pace.
            </p>
            <div className="inline-actions">
              <button className="button" onClick={beginTour} type="button">
                Start 2-minute tour <ArrowRight size={17} />
              </button>
              <button className="button-secondary" onClick={() => setMode("explore")} type="button">
                Explore freely
              </button>
            </div>
          </div>
          <div className="demo-welcome-summary" aria-label="Made-up July summary">
            <span>July 2026</span>
            <strong>{money(demo.summary.net)}</strong>
            <small>left after included spending</small>
            <div className="demo-mini-bars" aria-hidden="true"><i /><i /><i /><i /></div>
          </div>
        </section>
      ) : (
        <div className="demo-app-shell">
          <aside className="demo-sidebar" aria-label="Demo sections">
            <div className="demo-sidebar-brand">G<span>O</span>DFIN <small>public demo</small></div>
            <div className="demo-nav" role="tablist" aria-label="Explore the made-up household">
              {views.map(({ id, label, icon: Icon }) => (
                <button
                  aria-selected={view === id}
                  className={view === id ? "active" : ""}
                  key={id}
                  onClick={() => {
                    setMode("explore");
                    setView(id);
                  }}
                  role="tab"
                  type="button"
                >
                  <Icon size={16} /> {label}
                </button>
              ))}
            </div>
          </aside>
          <section className="demo-stage" role="tabpanel">
            {mode === "tour" ? (
              <div className="demo-tour-bar" aria-live="polite">
                <div>
                  <span>Step {tourIndex + 1} of {tourSteps.length}</span>
                  <strong>{tourSteps[tourIndex].title}</strong>
                  <p>{tourSteps[tourIndex].body}</p>
                </div>
                <div className="demo-tour-actions">
                  <button aria-label="Previous tour step" className="demo-icon-button" disabled={tourIndex === 0} onClick={() => moveTour(-1)} type="button"><ArrowLeft size={17} /></button>
                  <button className="button-secondary" onClick={() => setMode("explore")} type="button">Skip tour</button>
                  <button className="button" onClick={() => moveTour(1)} type="button">{tourIndex === tourSteps.length - 1 ? "Finish" : "Next"}<ArrowRight size={16} /></button>
                </div>
                <progress
                  aria-label="Tour progress"
                  className="demo-progress"
                  max={tourSteps.length}
                  value={tourIndex + 1}
                />
              </div>
            ) : null}

            <h2 className="demo-view-heading" ref={headingRef} tabIndex={-1}>
              {views.find((item) => item.id === view)?.label}
            </h2>

            {view === "overview" ? (
              <div className="demo-view">
                <div className="demo-period-row"><span>July 2026</span><span>Finalized month</span></div>
                <div className="demo-metric-grid">
                  <article><span>Money in</span><strong>{money(demo.summary.income)}</strong><small>verified salary + freelance</small></article>
                  <article><span>Included spending</span><strong>{money(demo.summary.spend)}</strong><small>3 spending transactions</small></article>
                  <article className="accent"><span>Left this month</span><strong>{money(demo.summary.net)}</strong><small>{demo.summary.savings_rate}% of verified income</small></article>
                  <article className="warning"><span>Account balance</span><strong>Unavailable</strong><small>{demo.summary.balance_reason}</small></article>
                </div>
                <div className="demo-chart-card">
                  <div><span>Where included spending went</span><strong>{money(demo.summary.spend)}</strong></div>
                  <div className="demo-donut" aria-label="₹10,000 food and dining and ₹1,000 entertainment"><span>91%<small>food</small></span></div>
                  <ul><li><i className="food" /> Food & dining <strong>₹10,000</strong></li><li><i className="fun" /> Entertainment <strong>₹1,000</strong></li></ul>
                </div>
              </div>
            ) : null}

            {view === "transactions" ? (
              <div className="demo-view">
                <label className="demo-search"><Search size={16} /><span className="sr-only">Search made-up transactions</span><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search this made-up month" /></label>
                <p className="demo-helper">Credits, transfers, refunds, and reversals are kept separate so the month is not overstated.</p>
                <div className="demo-transaction-list">
                  {filteredTransactions.map((row) => (
                    <article key={row.id}>
                      <div><span>{row.date}</span><strong>{row.merchant}</strong><small>{row.category}</small></div>
                      <div className="demo-transaction-amount"><strong className={row.direction}>{row.direction === "credit" ? "+" : "−"}{money(row.amount)}</strong><button aria-expanded={reasonId === row.id} onClick={() => setReasonId(reasonId === row.id ? null : row.id)} type="button">Why?</button></div>
                      {reasonId === row.id ? <p className="demo-reason"><CheckCircle2 size={15} /> {row.reason}</p> : null}
                    </article>
                  ))}
                </div>
              </div>
            ) : null}

            {view === "bills" ? (
              <div className="demo-view">
                <div className="demo-report-hero"><span>Regular commitments</span><strong>{money(demo.subscriptions.monthly)} / month</strong><small>{money(demo.subscriptions.annual)} across a full year if nothing changes</small></div>
                <div className="demo-simple-list">
                  {demo.subscriptions.items.map((item) => <article key={item.name}><div><strong>{item.name}</strong><small>{item.category} · monthly</small></div><strong>{money(item.monthly)}</strong></article>)}
                </div>
                <div className="demo-learning-note">GODFIN shows patterns for review. It does not cancel, renew, or change a payment.</div>
              </div>
            ) : null}

            {view === "goal" ? (
              <div className="demo-view">
                <div className="demo-goal-card"><span>Emergency cushion</span><h3>{demo.goal.name}</h3><div className="demo-goal-number"><strong>{money(demo.goal.saved)}</strong><span>of {money(demo.goal.target)}</span></div><div className="demo-goal-track"><i /></div><small>16% complete · history shown below</small></div>
                <div className="demo-simple-list">
                  {demo.goal.entries.map((entry) => <article key={entry.label}><div><strong>{entry.label}</strong><small>Recorded in the goal history</small></div><strong>{Number(entry.amount) >= 0 ? "+" : "−"}{money(String(Math.abs(Number(entry.amount))))}</strong></article>)}
                </div>
              </div>
            ) : null}

            {view === "report" ? (
              <div className="demo-view">
                <div className="demo-report-hero"><span>Your July money story</span><strong>{money(demo.summary.net)} left</strong><small>after {money(demo.summary.spend)} of included spending</small></div>
                <div className="demo-report-grid">
                  <article><span>Net worth in this demo</span><strong>{money(demo.net_worth.net)}</strong><small>{money(demo.net_worth.assets)} assets less {money(demo.net_worth.liabilities)} liabilities</small></article>
                  <article><span>Financial-year evidence</span><strong>{money(demo.financial_year.income)}</strong><small>verified income across {demo.financial_year.transactions} active rows</small></article>
                </div>
                <div className="demo-advice-list"><article><CheckCircle2 /><div><strong>Your regular bills are visible</strong><p>₹1,830 a month is easy to compare with the things you actually use.</p></div></article><article><CheckCircle2 /><div><strong>Your goal moved forward overall</strong><p>A ₹10,000 deposit and ₹2,000 withdrawal leave a clear ₹8,000 balance.</p></div></article><article className="warning"><LockKeyhole /><div><strong>Balance needs review</strong><p>Conflicting statement controls mean GODFIN leaves the balance unavailable instead of guessing.</p></div></article></div>
                <p className="demo-filing-note">This is a personal-finance summary. Transaction data alone cannot choose or file an Indian tax return.</p>
              </div>
            ) : null}

            {view === "privacy" ? (
              <div className="demo-view demo-privacy-view">
                <LockKeyhole size={34} />
                <h3>This page is a safe illustration.</h3>
                <p>Every name and amount comes from GODFIN’s synthetic acceptance ledger. This demo has no upload control, bank connection, website account, payment request, Gmail access, or AI request.</p>
                <div className="demo-boundary"><article><strong>Desktop app</strong><span>Ordinary statements, transactions, categories, goals, reports, and the local PIN stay on the computer.</span></article><article><strong>Website</strong><span>Waitlist consent, selected beta access, licenses, and feedback only when you choose those flows.</span></article></div>
              </div>
            ) : null}
          </section>
        </div>
      )}
    </div>
  );
}
