# OpenDataLoader extraction decision

Status: benchmark-ready, not shipped.

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
