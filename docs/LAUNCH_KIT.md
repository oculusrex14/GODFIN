# GODFIN launch kit — prepared, not published

Nothing in this file authorizes a public release. Publish only after the owner
approves the signed build, production website, pricing, support address, and
final screenshots.

## Launch-day order

1. Verify the private release checklist in `PRODUCTION_RELEASE.md`.
2. Publish the website and immutable signed download URLs.
3. Publish the reviewed GitHub release and update feed.
4. Submit Product Hunt.
5. Post Show HN.
6. Publish the X thread and LinkedIn post.
7. Share tailored Reddit posts only where self-promotion rules permit.
8. Publish the five-minute YouTube walkthrough.
9. Monitor checkout starts, successful one-time purchases, downloads, license
   activations, errors, refunds, and support volume.

## One-sentence pitch

GODFIN is a local-first personal finance desktop app for HDFC users: statements,
transactions, budgets, and reports stay in SQLite on your laptop, with a free
Core edition and optional lifetime Pro/Max licenses.

## Product Hunt

**Tagline**

Private personal finance for India—on your laptop

**Description**

GODFIN imports HDFC savings and credit-card statements, learns merchant
categories, matches transfers, and exports April–March financial-year data for
your CA. The desktop database stays local. Core is free; Pro and Max are
one-time purchases, not subscriptions.

**Maker comment**

I built GODFIN because bank data felt like the worst possible input for
cloud-first software. The desktop app runs React and FastAPI locally, stores its
ledger in SQLite, binds to localhost by default, and works without a GODFIN
account. The website only handles marketing, one-time payments, license records,
downloads, and optional AI credits.

The launch build supports HDFC statement formats. Other banks are a parser
roadmap, not a launch claim. I would especially value feedback on first-run
onboarding, statement reconciliation, and whether the privacy boundary is
explained clearly enough.

**Media checklist**

- 45–60 second GIF: PIN → upload redacted statement → review → dashboard.
- Real dashboard screenshot from the signed candidate.
- Cash-flow calendar screenshot.
- Transfer-match screenshot using synthetic accounts.
- Privacy diagram from the website.

## Show HN

**Title**

Show HN: GODFIN – local-first personal finance for HDFC statements

**Post**

I built GODFIN, a desktop personal-finance app whose transaction database stays
on your machine.

The app bundles a React 19 UI with a local FastAPI process and SQLite/WAL. It
imports HDFC savings and credit-card PDF/XLS/XLSX statements, reconciles
duplicates, classifies merchants with deterministic rules first, and provides
budgets, transfer matching, a cash-flow calendar, recurring-payment review, and
April–March exports.

The interesting boundary is architectural: the website can sell a lifetime
license, but it never becomes the application backend. Core works without an
account. Gmail, local embeddings, and BYO AI providers are opt-in. The app binds
to 127.0.0.1 unless the user explicitly enables LAN access.

The launch build supports HDFC; the parser registry is designed for other Indian
banks after each format is tested. I would appreciate critique of the local
process model, upgrade safety, and privacy explanation.

## Reddit

Use the community’s current self-promotion rules. Do not cross-post identical
copy or imply endorsement.

**r/IndiaInvestments draft**

I built a local-first expense and financial-year tracker for HDFC statements.
The statement data and transaction ledger stay in SQLite on your laptop; there
is no hosted financial database. It can reconcile repeat imports, review
merchant categories, match card-payment transfers, and export April–March
CSV/JSON for a CA.

Core is free. Paid editions are one-time lifetime licenses, not subscriptions.
The launch build supports HDFC; other bank parsers are still a roadmap. I would
value feedback on the FY export fields and the assumptions Indian users expect
from statement imports.

**r/personalfinance draft**

I made a desktop finance tracker for people who do not want their ledger in
another cloud account. React talks to FastAPI only on localhost, SQLite stores
the data, and the website is separated into a storefront/license service.

The app currently targets HDFC statement formats and Indian financial years.
I’m sharing the architecture and workflow, not presenting it as accounting or
tax advice. Feedback on reconciliation and local backup ergonomics is welcome.

## X thread

1. I built GODFIN because personal-finance software should not require handing
   your transaction history to another database.
2. The desktop app is React 19 + local FastAPI + SQLite/WAL. The backend binds
   to 127.0.0.1 by default.
3. Statement import, categorization, budgets, transfer matching, cash-flow
   calendar, and FY exports happen locally.
4. Gmail ingestion, embeddings, and BYO AI are optional. Deterministic rules
   keep the app useful without them.
5. The website is deliberately separate: marketing, one-time payments,
   licenses, downloads, and optional AI credits—no financial ledger.
6. Core is free. Pro and Max are lifetime licenses. No software subscription.
7. Launch support is HDFC savings and credit-card statements. Other banks ship
   only after their formats are verified.
8. [real app GIF] [pricing link] [technical architecture link]

## LinkedIn

Most finance products begin with a cloud account. I began with a boundary:
GODFIN’s transaction ledger must remain on the user’s machine.

That decision shaped the stack. Electron packages a React interface and a local
FastAPI service. SQLite runs in WAL mode. The service binds to localhost by
default. Optional Gmail and AI credentials are encrypted locally. The public
website is a storefront and license service, not an application database.

The launch build focuses on HDFC statements, reconciliation, category review,
budgets, cash flow, transfers, recurring payments, and Indian financial-year
exports. Core is free; paid editions use lifetime licenses rather than software
subscriptions.

The hardest engineering work was not a chart. It was restart-safe secrets,
expiring sessions, import integrity, local packaging, and an honest boundary
between commerce data and financial data.

## Five-minute YouTube demo

**0:00–0:25 — Promise**

Show the desktop app and say: “This is GODFIN. The transaction database is on
this laptop, not in a GODFIN cloud.”

**0:25–0:55 — First run**

Set a synthetic PIN, skip Gmail, and explain that Core needs no website account.

**0:55–1:40 — Import**

Upload the redacted fixture. Show preview, duplicate reconciliation, and the
structured import result.

**1:40–2:25 — Daily review**

Classify an unknown synthetic merchant, edit a draft transaction, and show that
a finalized month must be reopened.

**2:25–3:20 — Planning and insights**

Show a budget, subscription suggestion, cash-flow calendar, and transfer match.

**3:20–4:05 — Reports**

Generate a monthly PDF and FY April–March CSV/JSON export.

**4:05–4:35 — Privacy and settings**

Show service health, local backup, localhost/network toggle, account routing,
and optional Gmail/AI controls.

**4:35–5:00 — Pricing and limits**

Explain free Core, lifetime Pro/Max, local AI or bring-your-own provider keys,
zero included hosted credits, and that HDFC
is the launch parser while other banks remain on the roadmap.

## Measurement plan

Enable the consent-gated `NEXT_PUBLIC_GA_ID` only on the website. Track no
desktop telemetry. Review aggregate website events:

- landing page view;
- pricing view;
- download CTA;
- checkout start by product code;
- successful checkout confirmation;
- account sign-in;
- license resend;
- documentation search/referrer campaign.

Cashfree remains the source of truth for payment conversion. Supabase purchase
and license rows remain the source of truth for provisioning. Never send license
keys, emails, device hashes, statement names, or financial values to analytics.

Review at 24 hours, 72 hours, 7 days, and 30 days. Change one major landing-page
variable at a time and record the hypothesis before editing.
