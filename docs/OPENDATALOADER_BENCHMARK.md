# OpenDataLoader extraction decision

Status: evaluated on the owner acceptance set on 2026-08-25; not shipped.

GODFIN keeps statement parsing and financial reconciliation separate from
document extraction. The extractor-neutral `DocumentElement` and
`ExtractedDocument` intermediate representation is available for candidate
extractors, and the acceptance harness compares the decisive metric:
**complete reconciliation without manual correction**.

OpenDataLoader PDF is not bundled in the desktop application yet because its
official Python integration requires Java 11 or newer. Adding that runtime to
every installer is justified only after a privacy-safe corpus demonstrates a
material reconciliation gain.

## Acceptance gate

- Use 200–500 consented, fully redacted statement fixtures spanning supported
  banks and layouts.
- Never store real names, account/card numbers, UPI identifiers, addresses,
  emails, phone numbers, exact balances, or unredacted statement descriptions.
- Compare the current extractor and OpenDataLoader against the same parser and
  reconciliation checks.
- Require at least a five percentage-point gain in complete reconciliation
  without manual correction.
- Record extraction time, package size, Java startup cost, and failure rate.
- Ship only the deterministic local mode; any hybrid or remote mode requires a
  separate privacy and threat review.

Until that evidence exists, GODFIN continues to ship its current extractor and
does not silently install Java.

## 2026-08-25 owner-fixture evaluation

The private acceptance set contained one SBI multi-section relationship
statement, one HDFC savings statement, and one Kotak savings statement. Raw
files, names, account identifiers, narrations, dates, and financial control
values were not copied into the repository. The reusable verifier prints only
a source digest and pass/fail metadata.

| Extractor path | SBI | HDFC | Kotak | Result |
|---|---:|---:|---:|---|
| GODFIN `pdfplumber` profiles after certified fixes | 29/29 rows, reconciled | 306/306 rows, reconciled | 497/497 rows, reconciled | Retain |
| OpenDataLoader 2.5.3 deterministic local JSON | 31 date-like rows, schema not safely certified | 290/306 rows, 13 continuity failures | 497 list items, but transaction columns were not retained as a certifiable table | Reject as production extractor |

OpenDataLoader processed the three-file batch in approximately 1.35 seconds
with about 374 MB peak resident memory in the isolated benchmark environment.
It required a separate Java 21 runtime and Python package. It did not use a
network service, and hybrid/AI mode was not enabled. The Java runtime and
OpenDataLoader package remain absent from GODFIN's production dependency and
installer manifests.

The decisive metric was complete financial reconciliation without manual
correction. The candidate produced no reconciliation gain and lost structural
information needed to prove debit/credit integrity for two layouts. GODFIN
therefore retains the smaller native path and leaves the candidate disabled.
This result does not certify every future layout; unsupported variants still
fail closed.

Official implementation references used for the isolated evaluation:

- [OpenDataLoader quick start](https://opendataloader.org/docs/quick-start-java)
- [OpenDataLoader PDF repository](https://github.com/opendataloader-project/opendataloader-pdf)
- [OpenDataLoader CLI reference](https://opendataloader.org/docs/reference/cli-options)

To re-run a private acceptance case without logging its contents:

```bash
backend/venv/bin/python scripts/verify_private_statement_fixture.py \
  /absolute/path/to/private-statement.pdf \
  --expected-profile hdfc_savings \
  --expected-count 306
```
