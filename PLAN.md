# GODFIN Business & Engineering Plan v2.0
## Local-First Personal Finance for India

**Last updated:** 2026-07-28

---

## Executive Summary

GODFIN is a local-first desktop app for Indian bank users. It parses HDFC/SBI/ICICI/Axis/Kotak statements and SMS alerts, classifies transactions using a 5-layer deterministic + AI engine, and generates tax-ready reports. All data lives in a local SQLite file. No cloud. No tracking. No lock-in.

This plan integrates our monetization strategy with a rigorous pre-launch engineering pass. The product philosophy is non-negotiable: **what we discussed here wins** — local-first, lifetime pricing, honest AI credits, and a public website as the storefront.

---

## Product Philosophy

> *"Your bank data never leaves your laptop. The software is free. The convenience is paid."*

| Principle | How We Deliver |
|---|---|
| **Local-first** | SQLite on disk, no remote database, optional encrypted backup to user-owned S3 |
| **Privacy-first** | PIN-protected, no telemetry without explicit opt-in |
| **Honest economics** | AI costs money per token → we charge per use, no fake "unlimited" plans |
| **No lock-in** | BYO API key option; CSV/JSON export always free; open-source core |
| **One-time purchase** | Indian users hate subscriptions; lifetime licenses feel like ownership |

---

## Tech Stack

| Component | Choice | Cost at Launch |
|---|---|---|
| **Desktop App** | Electron (React 19 + FastAPI backend bundled) | $0 |
| **Frontend** | React 19 + Tailwind CSS v4 + Vite (JS, not TS — existing codebase) | $0 |
| **Backend** | FastAPI + Python 3.12 + SQLAlchemy + SQLite (WAL mode) | $0 |
| **Website** | Next.js 15 on Vercel | $0 (hobby) |
| **Auth** | Supabase Auth (email + Google OAuth) | $0 (free tier) |
| **Database (web)** | Supabase Postgres | $0 (free tier) |
| **Payments** | Stripe India | 2% + ₹3 per transaction |
| **Binary Storage** | Cloudflare R2 | ~$0 |
| **Email** | Resend | $0 (3K/month free) |
| **License Server** | Next.js API routes on Vercel | $0 |

---

## Website: godfin.dev

The website IS the business. For local-first software, it is storefront, billboard, trust engine, and payment gateway combined.

```
godfin.dev/
├── /                 → Landing page (hero, screenshots, features, CTAs)
├── /download         → OS detection, latest release binaries
├── /pricing          → Free vs Pro vs Max comparison table
├── /docs             → Setup guide, bank-specific parsers, FAQ, troubleshooting
├── /blog             → SEO articles (2/month minimum)
├── /privacy          → Required for Google OAuth verification
├── /terms            → Standard ToS
├── /changelog        → Release history
├── /account          → License management, credit balance, downloads
└── /api/webhook      → Stripe webhooks for license provisioning
```

### Landing Page Copy

- **Headline:** *"The Finance App That Respects Your Privacy"*
- **Subheadline:** *"GODFIN runs entirely on your laptop. Your bank data never touches our servers. Parse HDFC, SBI, ICICI, Axis, and Kotak statements with AI-powered classification. Generate tax reports. All offline."*
- **CTA Primary:** *"Download Free for macOS"*
- **CTA Secondary:** *"See Pricing →"*
- **Trust Badges:** Open source · Local-first · No subscription · Indian banks

### Payment Flow

1. User clicks **"Get Pro — ₹4,999"** on `/pricing`
2. Stripe Checkout opens → user pays
3. Webhook hits `/api/webhook` → Supabase function generates license key
4. License key emailed + shown on confirmation screen
5. User opens GODFIN app → Settings → "Enter License Key"
6. App pings `/api/license/verify` → unlocks Pro features

### Free User Flow

1. Discovers via blog post / Reddit / Product Hunt / search
2. Lands on `godfin.dev` → clicks "Download Free"
3. OS auto-detected → downloads Core build
4. Opens app → sets PIN → starts tracking HDFC expenses
5. Uses for 2–3 weeks
6. Tries to add ICICI account → hits Pro gate
7. In-app upsell: *"Multi-bank support requires GODFIN Pro. Upgrade for ₹4,999 lifetime."*
8. Clicks → browser opens `/pricing` → pays → enters key → done

---

## Monetization: Tier Structure

### 🟢 GODFIN Core — Free Forever

**No account required. No email. No telemetry.**

- Single bank account (HDFC)
- Manual PDF statement upload
- Rule-based + fuzzy classification (Layers 1–3)
- Dashboard, budgets, basic reports
- CSV export
- Local SQLite storage

**Why free:** Pure software costs us $0 to run per user. This is the distribution engine.

---

### 🔵 GODFIN Pro — ₹4,999 Lifetime

**Requires account (for license + credit tracking).**

- Multi-bank support (SBI, ICICI, Axis, Kotak)
- AI Classification (Layers 4–5) — **500 credits/month included**
- Advanced Reports — Tax P&L, capital gains, trend forecasting
- Encrypted Cloud Backup — sync to user-owned S3 or our managed R2
- Multi-device sync (optional, encrypted)
- Priority support (Discord / email)

---

### 🟣 GODFIN Max — ₹9,999 Lifetime

**For power users, CAs, family offices.**

- **2,500 AI credits/month**
- Family mode — up to 5 profiles under one license
- White-label reports (custom branding for CA firms)
- Local REST API access
- Early access to new bank parsers (30 days before Pro)

---

### AI Credit System

| Operation | Credits |
|---|---|
| Embedding similarity (Layer 4) | 1 |
| LLM classification (Layer 5) | 5 |
| Financial insights report | 10 |
| Report commentary generation | 15 |

**Top-up Packs:**

| Pack | Price | Credits | Effective Rate |
|---|---|---|---|
| Starter | ₹249 | 500 | ₹0.50/credit |
| Regular | ₹499 | 1,200 | ₹0.42/credit |
| Power | ₹999 | 3,000 | ₹0.33/credit |

**BYO Key Escape Valve:** Users can add their own OpenAI/Anthropic/Google/Ollama API key in Settings to bypass the credit system entirely. This removes lock-in objections.

**Credit UX:**
- Banner at 80% usage: *"You've used 400 of 500 AI credits. Top up to keep AI classification running."*
- At 0%: fallback to rule-based classification (Layers 1–3). App never breaks.

---

## Revenue Model

| Stream | Mechanism | Margin |
|---|---|---|
| Pro Lifetime Licenses | Stripe one-time | ~97% |
| Max Lifetime Licenses | Stripe one-time | ~97% |
| Credit Top-ups | Stripe one-time | ~60% |
| Affiliate Links (future) | Credit cards, mutual funds in reports | Variable |

---

## Revenue Projections (Conservative)

| Metric | Month 6 | Month 12 | Month 24 |
|---|---|---|---|
| Website Visitors | 1,000/mo | 3,000/mo | 8,000/mo |
| Free Downloads | 200/mo | 600/mo | 1,500/mo |
| Active Free Users | 400 | 1,200 | 3,000 |
| **Pro Conversions (5%)** | 20 | 60 | 150 |
| **Max Conversions (1%)** | 4 | 12 | 30 |
| License Revenue | ₹1.4L | ₹4.2L | ₹10.5L |
| Credit Top-ups | ₹3K | ₹10K | ₹25K |
| **Monthly Revenue** | **₹1.43L** | **₹4.3L** | **₹10.75L** |
| **Annual Revenue** | **₹8.6L** | **₹51.6L** | **₹1.29Cr** |

*Conservative. Assumes no churn on lifetime licenses (true by design).*

---

## Pre-Launch Engineering: P0 Bug Fixes

**These must be resolved before the website goes live.** A broken encryption key or immortal auth token will destroy trust on day one.

### 1. Stable Encryption Key (Grok #1)

**Problem:** `encryption.py` generates a random Fernet key if `ENCRYPTION_KEY` is unset. Key dies on restart → Gmail/LLM secrets decrypt to garbage.

**Fix:**
- Load key from env → macOS Keychain → `backend/data/.encryption_key` (0600 perms, gitignored)
- Fail hard at startup if encrypted blobs exist but key is missing
- Add Settings health indicator: "Encryption key: OK / Missing / Rotated"
- Recovery path: "Re-auth Gmail / Re-enter LLM key" when decrypt fails

```python
def _get_encryption_key() -> bytes:
    key = load_from_env() or load_from_keychain() or load_from_file()
    if key is None:
        if encrypted_data_exists():
            raise RuntimeError("ENCRYPTION_KEY missing; cannot decrypt secrets")
        key = Fernet.generate_key()
        persist_key(key)
    return key
```

### 2. Decrypt LLM Keys on Startup (Grok #2)

**Problem:** LLM config loaded at startup passes ciphertext straight into provider.

**Fix:**
- Always `decrypt(config.api_key)` before `create_provider()`
- Same fix in `activate_llm_config`
- Add unit test: encrypt → save → simulate restart → verify provider receives plaintext

### 3. Real Token Expiry (Grok #3)

**Problem:** Auth token restored from DB with `expires_at = inf`. Combined with `0.0.0.0` binding, LAN theft = permanent access.

**Fix:**
- Store `expires_at` in DB alongside token; enforce on every request
- Logout clears DB token + rotates session ID
- Default bind: `127.0.0.1` (localhost only)
- Add "Allow network access" toggle in Settings → binds `0.0.0.0` only when explicitly enabled
- Optional: single active session (new login invalidates old)

### 4. PIN Rate Limit Per Client (Grok #4)

**Problem:** Rate limit keyed as `"local"` — all users share one bucket.

**Fix:**
- Use `Request.client.host` as rate limit key
- Persist attempt counters in SQLite (survives restarts)
- Only trust `X-Forwarded-For` if behind a known reverse proxy

### 5. Statement Import Never 500s (Grok #5)

**Problem:** Merchant memory `UNIQUE` constraint can fail mid-import.

**Fix:**
- One shared `upsert_merchant_memory()` used by statement, review, ingestion
- Use SQLite `INSERT ... ON CONFLICT(normalized_name) DO UPDATE`
- Never fail the entire import for merchant memory — log and continue
- Return structured import report: `{imported: N, skipped_dup: M, classified: K, review_queue: R, errors: []}`

---

## Pre-Launch Engineering: P1 UX Improvements

These turn "works" into "delightful."

### 6. Edit Without Audit Session (Grok #6)

**Problem:** Edit/delete hidden behind `isAuditActive`. Personal trackers shouldn't need a formal audit session to fix a Swiggy category.

**Fix:**
- Always allow edit/delete on **draft** months (no audit session required)
- On **finalized** months: read-only with "Reopen audit to edit" CTA
- Keep audit as **batch finalize + freeze aggregates**, not as a gate on every pencil icon

### 7. Debounced Search + URL Filters (Grok #7, #11)

**Problem:** Search fires API on every keystroke. Refresh loses filter state.

**Fix:**
- 300ms debounce on search input before API call
- Minimum 2 characters before triggering search
- Sync filters to URL query params: `?q=swiggy&category=FOOD&page=2`
- URL is single source of truth; shareable/bookmarkable filtered views

### 8. Dashboard Month Selector (Grok #8)

**Problem:** Month picker only shows Jan → current month of current year. Historical data invisible.

**Fix:**
- Query actual transaction months: `SELECT DISTINCT strftime('%Y-%m', date) FROM transactions ORDER BY 1 DESC`
- Fallback: last 24 months
- Add year navigation (prev/next year buttons)

### 9. Single Taxonomy Source (Grok #9)

**Problem:** Categories defined in `classifier.py`, `taxonomy.py`, and `frontend/src/data/taxonomy.js` — already drifted (`Bank Charges` missing from frontend).

**Fix:**
- **Backend is source of truth:** `taxonomy.py` owns all categories
- Add `GET /api/v1/taxonomy` endpoint
- Frontend fetches taxonomy on mount, caches in React Query
- Delete duplicate `TAXONOMY` dict in `classifier.py`; import from `taxonomy.py`
- Add test: assert frontend category set === backend category set

### 10. Global Error Toast (Grok #10)

**Problem:** Backend errors logged server-side; UI looks fine. Users think the app is broken silently.

**Fix:**
- Standard API error shape: `{code, message, hint, retriable}`
- React Query `onError` → toast notification
- Settings health card: Gmail (connected / needs re-auth), LLM (ok / decrypt failed), last ingest, last backup
- Never swallow network/auth errors

### 11. Navigation Regroup (Grok #12)

**Problem:** 11 top-level nav items is too many for a single-user app.

**Fix:**
- **Daily:** Dashboard, Transactions, Review, Upload
- **Plan:** Budget, Subscriptions, Income
- **Insights:** Reports, Advisor
- **System:** Audit, Settings
- Collapse secondary items under groups or a "More" drawer on mobile

---

## Pre-Launch Engineering: P2 Cleanup

These prevent maintenance tax from compounding.

### 12. Delete Dead Modules (Grok #13)

- `merchant_merger.py` vs `merchant_merging.py` → keep `merging`, delete `merger`
- `rule_generation.py` vs `rule_generator.py` → keep `generator`, delete `generation`
- `report_pdf.py` → merge into `reporting.py` or extract to `reports/pdf.py`

### 13. Multi-Account Plugin Shape (Grok #14)

**Problem:** Seeds, parsers, and transfer keywords hardcode HDFC 0952 + Swiggy CC 2476.

**Fix:**
- Accounts are fully CRUD in Settings (already partially there)
- Pluggable parser directory: `parsers/hdfc_savings.py`, `parsers/hdfc_cc.py`, later `parsers/icici.py`
- Sender → account mapping as DB config, not code constants
- Keep HDFC as default profile, not the only architecture

### 14. Optional Embeddings (Grok #15)

**Problem:** `sentence-transformers` + `torch` is heavy for a local app.

**Fix:**
- Layer 4 (embeddings) is **already optional** in settings — verify this works cleanly
- On first enable: download model on-demand with progress indicator
- Default path: Layers 1–3 only (fast, no downloads)
- Add Settings toggle: "Enable embedding classification (downloads ~100MB model)"

### 15. Session Table (Grok #16)

**Problem:** Auth is in-memory dict + single DB token. Fails under multi-worker uvicorn.

**Fix:**
- Create `sessions` table: `token_hash, expires_at, created_at, user_agent, ip_address`
- Hash tokens at rest (like passwords)
- Cap concurrent sessions at 3 (configurable)
- On new login: invalidate oldest session if at cap

### 16. API Client Refactor (Grok #17)

**Problem:** `client.js` is 646 lines with two request helpers and duplicated 401 handling.

**Fix:**
- One `apiFetch` helper with unified 401 → redirect to `/pin`
- Group exports by domain: `transactionsApi`, `auditApi`, `reportsApi`, `settingsApi`
- Or generate from OpenAPI schema (future)

### 17. Repo Hygiene (Grok #19)

**Problem:** Real bank statements, screenshots, junk filenames in repo.

**Fix:**
- `.gitignore`: `*.xls`, `*.pdf`, `screenshots/`, `logs/`, `backups/`, `godfin_startup.log`, `*.db`, `*.db-shm`, `*.db-wal`
- Move sample data to `backend/data/samples/` with redacted values only
- Move docs to `docs/` directory
- Rotate any Google client secret that ever lived in git history
- Clean root: no loose files

### 18. Backup Retention (Grok #20)

**Problem:** `backend/backups/` grows unbounded.

**Fix:**
- Keep: last 7 daily + last 4 weekly backups
- Prune on scheduler tick (every nightly batch)
- Settings option: backup directory path (default: `./backups`)
- Optional: encrypted zip to user-specified external path

---

## Pre-Launch Engineering: P3 Product Depth

These differentiate GODFIN from Excel / Money Manager.

### 19. Cash-Flow Calendar

Month heatmap showing spend + income days. Click a day → see transactions.

### 20. Transfer Matching UI

Explicit "Match Transfer" workflow: CC payment ↔ savings debit. Prevents double-counting spend. "Confirm / Ignore / Snooze" for ambiguous pairs.

### 21. Subscription Confirmations

Currently passive detection. Add:
- "Confirm / Ignore / Snooze" workflow for detected subscriptions
- Upcoming bill reminders (7 days before)
- Annual vs monthly toggle

### 22. Advisor Weekly Digest

Replace static Advisor page with proactive weekly email (optional, local-only):
- Top 3 anomalies
- Budget breaches
- New merchants detected
- Spending velocity vs last month

### 23. FY Export + Better Reports

- One-click "Export for CA" — FY Apr-Mar CSV/JSON with all metadata
- Pin "story" sections in Reports: "What changed vs last month"
- Compare to reference design (our existing Reports page is strong, build on it)

### 24. Mobile Responsive + Bottom Nav

- Responsive bottom nav for phone access over LAN
- Large tap targets (>44px)
- Touch-optimized PIN input

### 25. First-Run Onboarding Wizard

1. Set PIN
2. Connect Gmail (optional skip)
3. Upload one statement
4. Review and classify 10 transactions
5. Dashboard preview

---

## Testing & CI

### Playwright
- Convert `// BUG:` comments to `@fixme` or failing tests
- `headless: true` in CI; `headless: false` only locally
- Smoke test: login → upload statement → classify → generate report

### CI Pipeline (GitHub Actions)
```yaml
# .github/workflows/ci.yml
on: [push, pull_request]
jobs:
  backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - run: pip install -r backend/requirements.txt
      - run: pytest backend/tests/ -q
  frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20' }
      - run: cd frontend && npm ci && npm run build
  e2e:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: cd playwright-tests && npm ci && npx playwright install
      - run: npx playwright test --headless
```

### Spec Alignment
- Update `GODFIN_Final_Build_Specification` to reflect actual ports (5100/5200)
- Pin `requires-python = ">=3.12"` in `pyproject.toml`
- Document: SQLite `create_all + seed` is the migration strategy (honest, no Alembic drift)

---

## Implementation Roadmap

### Phase 0: Trust & Hardening (Weeks 1–2)
**Goal:** Fix every P0 bug. App must survive restart without losing Gmail/LLM/auth.

- [ ] 1. Stable encryption key (env → keychain → file fallback)
- [ ] 2. Decrypt LLM keys on boot + unit test
- [ ] 3. Real token expiry + localhost default bind
- [ ] 4. Shared merchant upsert with `ON CONFLICT` — import never 500s
- [ ] 5. PIN rate limit per client IP, persisted in SQLite
- [ ] 6. Surface Settings health errors in UI (Gmail, LLM, backup status)
- [ ] 7. Delete dead modules (`merchant_merger`, `rule_generation`)
- [ ] 8. Repo hygiene: `.gitignore`, clean root, redact samples
- [ ] 9. Backup retention policy (7 daily + 4 weekly)
- [ ] 10. Session table with token hashing + 3-session cap

**Deliverable:** Backend survives restart, Gmail reconnects, LLM activates, auth expires properly.

---

### Phase 1: Daily UX (Weeks 3–4)
**Goal:** Remove friction from every daily interaction.

- [ ] 11. Allow edit/delete on draft months without audit session
- [ ] 12. Finalized months: read-only with "Reopen to edit" CTA
- [ ] 13. Debounced search (300ms) + min 2 chars
- [ ] 14. URL query params for filters (?q=&category=&page=)
- [ ] 15. Dashboard month selector from actual data (last 24 months)
- [ ] 16. Single taxonomy source (`taxonomy.py` + `GET /api/v1/taxonomy`)
- [ ] 17. Global error toast from React Query `onError`
- [ ] 18. Nav regroup: Daily / Plan / Insights / System
- [ ] 19. API client refactor: one `apiFetch`, domain groupings
- [ ] 20. Optional embeddings: download on first enable with progress

**Deliverable:** App feels polished, fast, and forgiving.

---

### Phase 2: Website & Payments (Weeks 5–8)
**Goal:** Storefront is live. Users can download, pay, and unlock.

- [ ] 21. Buy domain (`godfin.dev` or similar)
- [ ] 22. Build Next.js landing page (hero, features, screenshots, pricing)
- [ ] 23. Build `/download` with OS detection
- [ ] 24. Build `/docs` with setup guides and bank-specific instructions
- [ ] 25. Deploy to Vercel + Supabase project
- [ ] 26. Stripe integration: Pro lifetime, Max lifetime, credit packs
- [ ] 27. Webhook handler: `checkout.session.completed` → provision license
- [ ] 28. Resend email integration: license delivery, receipts
- [ ] 29. Add "Enter License Key" UI in Settings
- [ ] 30. Gate multi-bank + AI behind `license_tier !== 'free'`

**Deliverable:** `godfin.dev` is live with working payments.

---

### Phase 3: Packaging (Weeks 9–10)
**Goal:** Users install like a real app, not a GitHub project.

- [ ] 31. Electron wrapper for macOS/Windows/Linux
- [ ] 32. Auto-updater (Sparkle for macOS, electron-updater for Win/Linux)
- [ ] 33. Signed binaries (Apple Developer ID, Windows cert)
- [ ] 34. Homebrew cask: `brew install --cask godfin`
- [ ] 35. GitHub Releases with automatic asset attachment

**Deliverable:** One-click installer for all platforms.

---

### Phase 4: Product Depth (Weeks 11–14)
**Goal:** Differentiators that justify the price.

- [ ] 36. Cash-flow calendar heatmap
- [ ] 37. Transfer matching UI (CC payment ↔ savings debit)
- [ ] 38. Subscription confirmations + bill reminders
- [ ] 39. FY export for CA (Apr-Mar CSV/JSON)
- [ ] 40. Advisor weekly digest (local-only, optional)
- [ ] 41. Mobile responsive + bottom nav
- [ ] 42. First-run onboarding wizard

**Deliverable:** Pro features feel meaningfully better than free.

---

### Phase 5: Launch (Week 15)
**Goal:** Maximum visibility on launch day.

- [ ] 43. Product Hunt launch (scheduled, GIF demo, maker comment)
- [ ] 44. Hacker News "Show HN" post
- [ ] 45. Reddit: r/IndiaInvestments, r/personalfinance
- [ ] 46. Twitter/X thread (architecture, privacy angle, screenshots)
- [ ] 47. YouTube demo video (5 min screen recording)
- [ ] 48. LinkedIn post about building privacy-first software in India
- [ ] 49. Set up Google Analytics on website (privacy-respecting, anonymized)
- [ ] 50. Monitor Stripe conversions, iterate landing page copy

**Deliverable:** Public launch with measurable traffic.

---

### Phase 6: Growth (Month 4+)
**Goal:** Sustainable organic traffic and community.

- [ ] 51. Publish 2 SEO blog posts/month
- [ ] 52. Add new bank parsers (SBI → ICICI → Axis → Kotak)
- [ ] 53. GitHub Discussions or Discord community
- [ ] 54. Consider Setapp or App Store distribution
- [ ] 55. Iterate pricing based on conversion data
- [ ] 56. Add affiliate partnerships (credit cards, mutual fund platforms)

---

## Launch Content Calendar (First 3 Months)

| Month | Blog Post 1 | Blog Post 2 |
|---|---|---|
| 1 | "How to Track HDFC Bank Expenses Automatically" | "Building a 5-Layer Transaction Classifier" |
| 2 | "Best Offline Personal Finance App for India 2026" | "Parsing Indian Bank SMS Alerts with Regex" |
| 3 | "Why I Built a Local-First Finance App" | "GODFIN vs MoneyWiz: A Privacy Comparison" |

**Each post links to `godfin.dev` with a CTA.**

---

## Why This Plan Wins

| Competitor | Their Approach | GODFIN's Advantage |
|---|---|---|
| **MoneyWiz** | $60/year subscription, cloud lock-in | One-time purchase, data stays local |
| **Palmier Pro** | Free editor + expensive AI subs | Free core + affordable AI, Indian banks |
| **Actual Budget** | 100% free, sponsor-funded | Sustainable business, you can pay for value |
| **Typical SaaS** | Your data on their servers | Local-first, encrypted backup to YOUR S3 |
| **Excel** | Manual, no classification | AI-powered, built for Indian bank formats |

---

## One Sentence Pitch

> *"GODFIN is the personal finance app that runs on your laptop, not in the cloud. Track HDFC, SBI, ICICI, Axis, and Kotak expenses with AI-powered classification. Generate tax reports. Free forever for basic use. Upgrade once to unlock multi-bank support and advanced reports. Your data never leaves your machine."*

---

## Final Decision Points

| Question | Decision |
|---|---|
| **TypeScript?** | No. Existing React 19 + JS codebase is our stack. JSDoc + `// @ts-check` is acceptable for new files. |
| **Audit model change?** | Partial. Allow edits on draft months without active audit session. Keep finalize → lock for finalized months. |
| **Database switch?** | No. SQLite + WAL mode is our architecture. Optional encrypted sync to user-owned S3. |
| **Cloud hosting for app?** | No. Desktop Electron app only. Website is Next.js on Vercel. |
| **Subscription option?** | No. Only lifetime licenses. Optional AI credit top-ups. |
| **Open source?** | Yes. Core is open source (GitHub). Pro/Max features are closed-source binary gating. |

---

*This plan combines our monetization strategy with Grok's engineering critique. What we discussed here is the anchor. Grok's bugs and UX fixes are integrated. Conflicts resolved in our favor. Ready to build.*
