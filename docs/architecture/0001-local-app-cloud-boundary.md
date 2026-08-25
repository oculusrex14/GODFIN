# ADR-0001: Local app and cloud-service boundary

Status: Accepted
Date: 11 August 2026

## Context

GODFIN processes high-sensitivity personal financial records while also needing
a public website for discovery, account access, payments, and licensing.

## Decision

The Electron application bundles React and FastAPI and stores ordinary app data
in local SQLite. The app backend is never cloud-hosted. The Next.js website may
use Vercel, Supabase Auth/license metadata, Cashfree, and Resend, but receives no
desktop statements, ledger, PIN, merchant memory, budgets, or net-worth data.
Only a separately consented and locally redacted pilot contribution may cross
the boundary.

## Consequences

Offline deterministic features remain available. Cloud outages cannot corrupt
the ledger. Cross-device financial sync is not implied. Every new network call
must document its minimal payload and consent basis.
