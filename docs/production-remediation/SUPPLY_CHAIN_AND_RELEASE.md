# Dependency, supply-chain, and local package evidence

Recorded: 25 August 2026 (Asia/Kolkata)

This is evidence for a private candidate, not permission to publish an
installer or update feed.

## Dependency boundaries

GODFIN has three separately generated universal Python 3.12 hash locks:

- `requirements-lock.txt` — application runtime;
- `requirements-test-lock.txt` — identical runtime pins plus test tooling; and
- `requirements-build-lock.txt` — identical runtime pins plus frozen-build
  tooling.

The runtime excludes retired or unused hosted-AI SDKs, Python Levenshtein, and
test-only packages. The Google API client is an explicit runtime dependency for
Gmail. `scripts/verify_dependency_boundaries.py` rejects surface drift,
unhashed requirements, mismatched inherited pins, retired runtime imports, and
unreviewed generation commands.

The weekly private refresh workflow opens review PRs. `CODEOWNERS` covers
workflow, lock, SBOM, notice, license-policy, and provenance changes.

## Vulnerability and license inventory

The current deterministic CycloneDX 1.6 SBOM contains 1,035 unique components
and has SHA-256:

`3466efb089d51afc553d7b84bda156bc0e3420af808b38c93b17516aa37a5290`

`THIRD_PARTY_NOTICES.md` is generated from the same lock inputs. The generator
rejects missing license metadata, prohibited/unresolved expressions, stale
review entries, and stale output. Package verification requires byte-identical
PolyForm Noncommercial license, notices, SBOM, and legal-clearance evidence.

The four npm production trees and all three Python lock surfaces report no
accepted known vulnerability. `cryptography` is on the fixed 50.x line; the
former `PYSEC-2026-3552` exception is removed.

Conditional-license obligations, including `fpdf2` under LGPL-3.0-only, still
require qualified human review. `supply-chain/legal-clearance.json` remains
`pending`, so promotion fails closed.

## Exact-source CI

GitHub Actions run `32800966419` passed all seven jobs on exact source SHA
`b2dcaeccd237f5ae4e2076ca4959e5e329df72fe`:

- 1,008 backend tests and Python dependency audits;
- frontend lint, accessibility/content/auth contracts, controls, build, audit;
- website contracts, 11 unit tests, build, audit;
- Chromium/Firefox/WebKit app and website matrices;
- desktop privacy/integrity, update/release, and production dependency audits;
- a clean 11-migration Supabase database with all 107 pgTAP assertions; and
- full-history secret scanning.

The repository was returned to `PRIVATE` immediately after the run.

## Existing macOS arm64 private package evidence

The retained package proof predates the exact current source candidate. It is a
local ad-hoc hardened-runtime build, not a customer release. It verified bundled
backend auto-start, loopback trust, package privacy, database preservation,
restart behavior, and the recorded performance budget. Gatekeeper correctly
rejects it because it is neither Developer ID signed nor notarized.

No current-source signed/native claim is made from that historical artifact.
The exact current candidate must be rebuilt, signed, notarized where required,
and tested on clean supported systems.

## Release provenance and immutability

Release workflows bind exact tag, commit, version, artifact bytes, checksums,
SBOM, notices, legal evidence, and in-toto/SLSA-style provenance. Actions are
immutable-SHA pinned. Workflows refuse to replace an existing release and
require staged promotion plus provenance-checked immediate-predecessor
rollback.

## Remaining external release gates

- Qualified dependency-license and public legal review.
- Apple Developer ID signing/notarization for macOS arm64/x64.
- Windows Authenticode/SmartScreen evidence.
- Linux AppImage/deb clean-system evidence.
- Exact-current-source install, upgrade, rollback, uninstall/data-retention,
  offline, non-ASCII-path, endpoint-security, and Ollama matrices.
- R2 immutable release storage and staged health/rollback drills.
- Provider, recovery, independent pentest, and written owner authorization.

No workflow or artifact described here is a public-launch authorization.
