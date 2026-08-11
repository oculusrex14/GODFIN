# ADR-0005: Lifetime commerce and signed entitlements

Status: Accepted
Date: 11 August 2026

## Context

GODFIN needs paid desktop entitlements without subscriptions or a remote
financial database.

## Decision

Pro and Max are one-time lifetime licenses. Hosted AI credits, if offered, are
separate one-time packs; no recurring allowance is bundled. A shared entitlement
manifest controls app, website, checkout, and license behavior. License payloads
must be signed and verified locally with rotation support. A license permits at
most three user-managed installations.

## Consequences

Refunds/disputes must revoke entitlements. Website, verifier, and app require
cross-contract tests. Payment data and hardware identifiers are not copied into
the desktop database.
