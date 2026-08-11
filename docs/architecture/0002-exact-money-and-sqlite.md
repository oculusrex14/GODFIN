# ADR-0002: Exact money and local SQLite authority

Status: Accepted
Date: 11 August 2026

## Context

Binary floating-point storage and multiple remote authorities would make
financial reconciliation and recovery ambiguous.

## Decision

SQLite is the sole ordinary application database. Authoritative monetary values
use field-specific scaled integers with validated compatibility shadows during
migration. Calculations use decimal semantics and explicit rounding. Derived
projections are rebuildable; authoritative ledger records are never silently
deduplicated or corrected.

## Consequences

Schema and import changes require exact-value, control-total, round-trip, and
recovery tests. Supabase is not a replica of the desktop ledger.
