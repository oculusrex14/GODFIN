# ADR-0006: Private signed candidates before release promotion

Status: Accepted
Date: 11 August 2026

## Context

Desktop releases combine native binaries, schema upgrades, signatures,
notarization, update metadata, and user-data recovery risk.

## Decision

CI builds immutable native artifacts and a private draft release. Each candidate
must pass package privacy, signatures/fuses, checksums, clean-machine startup,
upgrade/rollback, database preservation, and performance gates. Update metadata
is promoted separately only after owner authorization. Source success alone
cannot authorize public distribution.

## Consequences

Release credentials stay in provider secret stores. A failed native platform
blocks that release. Public launch and update promotion remain explicit owner
actions.
