# GODFIN production release runbook

This runbook is intentionally split into preparation and public release. A
public website, public repository, signed binary, or store listing must not be
published until the owner explicitly authorizes the release.

## 1. Repository and privacy gate

- Confirm the GitHub repository is private.
- Rewrite any history that ever contained OAuth credentials, API keys, real
  statements, database files, screenshots with financial data, or logs.
- Rotate every credential that ever appeared in history.
- Run a secret scan against the full rewritten history.
- Confirm the root license is PolyForm Noncommercial 1.0.0.
- Confirm only synthetic/redacted fixtures and screenshots are tracked.

## 2. Automated verification

```bash
backend/venv/bin/python -m pytest -q backend/tests
cd frontend && npm ci && npm run lint && npm run build
cd ../website && npm ci && npm run build && npm audit --omit=dev
cd ../playwright-tests && npm ci && npx playwright test
```

GitHub Actions must pass backend, frontend, website, Electron packaging smoke,
and Playwright jobs on the release commit.

## 3. Website services

- Supabase migration applied; RLS policies manually verified with two test
  users.
- Google OAuth consent, domain, callback, privacy page, and terms page verified.
- Stripe products are one-time INR prices with exact server-side amounts.
- Stripe webhook signature failure returns HTTP 400.
- A Stripe test payment provisions exactly one purchase/license and one email,
  including after webhook replay.
- A credit-pack test payment increments the balance exactly once.
- Resend domain DKIM/SPF passes and delivery is tested on Gmail plus one other
  provider.
- Production environment variables are present in Vercel and absent from git.
- `godfin.dev`, HTTPS, sitemap, robots, security headers, and 404 behavior pass.

## 4. Desktop signing and updates

- macOS Developer ID Application signing and notarization pass on Apple silicon
  and Intel.
- Windows code signing passes SmartScreen checks on a clean VM.
- Linux AppImage launches on the oldest supported distribution.
- The bundled FastAPI process binds to `127.0.0.1` by default.
- Installer, upgrade, rollback, uninstall, data retention, and backup restore
  are tested on clean machines.
- Auto-update metadata and release artifacts are signed and checksummed.
- The previous stable version can update to the candidate without losing the
  SQLite database, encryption key, license, or Gmail/LLM credentials.
- Confirm the draft release includes `release-compatibility.json`, its app
  version matches the tag, its schema revision matches the binary, and its
  `previous_release_version` is the reviewed immediate predecessor.
- Start promotion at 5% using `PUBLISH_STAGED_RELEASE`. Do not advance to 25%,
  50%, or 100% until the owner has reviewed the clean-machine startup,
  migration, import, backup, and support/error evidence and enters
  `ADVANCE_AFTER_HEALTH_REVIEW` in the protected release environment.
- For rollback, provide both the currently published tag and its declared
  immediate predecessor. The workflow must reject skipped versions, verify both
  checksum sets, and publish rollback metadata at 100% only after the desktop
  has restored the verified pre-upgrade SQLite snapshot.
- Exercise an interrupted rollback: after snapshot restoration but before
  installer launch, restart the current build and confirm its preserved current
  database is restored automatically. Then repeat and allow the predecessor to
  start, confirming its journal status becomes completed.

## 5. Functional acceptance

- First run: PIN → optional Gmail skip → statement upload → review → dashboard.
- Draft transactions can be edited/deleted; finalized months remain locked
  until reopened.
- HDFC works in Core; non-HDFC and AI calls show a clear Pro gate.
- License activation, invalid key, device limit, offline grace, expired grace,
  and re-verification are tested.
- Statement imports produce structured errors and never fail because merchant
  memory already exists.
- Transfer matching prevents confirmed card payments from being double-counted.
- FY Apr–Mar CSV and JSON exports reconcile to source transactions.
- Cash-flow calendar day totals reconcile to dashboard totals.
- Subscription confirm/ignore/snooze and reminders persist after restart.
- Mobile LAN view has a bottom nav, 44px targets, and touch PIN entry.

## 6. Public release

- Attach signed installers, blockmaps/update metadata, checksums, SBOM, and
  release notes to a private draft GitHub Release.
- Point website download variables to those immutable release assets.
- Run a final production payment with a low-value test product, then remove it.
- Capture the final website and app screenshots from the shipped build.
- Obtain explicit owner authorization.
- Publish the website, GitHub Release, Homebrew cask, and prepared launch
  content in the agreed order.
