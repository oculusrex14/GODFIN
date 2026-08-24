# Statement parser plugins

Statement parsing is routed through `backend/app/core/parsers/`. Each plugin
declares:

- a stable parser profile used by Gmail sender mappings;
- its bank and account type;
- its emitted statement type;
- supported file formats;
- a conservative text detector;
- a parse function returning `StatementParseResult`.

The registry sniffs PDFs and requires exactly one matching plugin; it never
falls through to a weaker parser. Certified PDF profiles currently cover HDFC
savings, HDFC credit cards, Kotak savings, and SBI savings relationship
statements. HDFC savings also supports XLS and XLSX.

Savings profiles must preserve explicit debit and credit columns, reconstruct
split table segments, verify row-by-row running balances, compare every
available statement summary control, and establish account identity where the
source provides it. A mismatch rejects the complete file before any ledger
write. SBI relationship statements with multiple savings sections require the
user to select the matching configured account.

## Adding another bank

1. Add a module such as `parsers/icici.py` with one plugin per account format.
2. Register it in `registered_parsers()`.
3. Add only synthetic/redacted fixtures for each supported export variation.
4. Test detection, parse errors, amounts, dates, credits/debits, and duplicate
   upload reconciliation.
5. Add a sender pattern and parser profile from **Settings → Accounts & Import
   Routing**. The mapping is stored in local SQLite, not in source constants.
6. Verify the Pro/Max multi-bank gate before exposing the parser in the UI.

Parser modules must never log raw statement text or account numbers. Unknown
formats return a structured 400 response instead of a server error.
