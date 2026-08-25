# ADR-0004: Separate website and desktop OAuth clients

Status: Accepted
Date: 11 August 2026

## Context

Website sign-in and Gmail transaction ingestion have different trust models,
redirects, scopes, and user expectations.

## Decision

Website Google sign-in is configured through a dedicated Supabase/Google web
client requesting identity scopes only. Desktop Gmail uses a separate installed
application client and fixed loopback callback, with import scopes minimized.
Secrets and tokens are never shared between the two clients or committed.

## Consequences

Provider dashboards must contain two clearly named clients. Redirect URIs,
consent text, rotation, and incident response are verified independently.
