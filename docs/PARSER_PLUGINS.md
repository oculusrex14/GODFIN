# Statement parser plugins

Statement parsing is routed through `backend/app/core/parsers/`. Each plugin
declares:

- a stable parser profile used by Gmail sender mappings;
- its bank and account type;
- its emitted statement type;
- supported file formats;
- a conservative text detector;
- a parse function returning `StatementParseResult`.

The registry sniffs PDFs, selects a matching plugin, and retains ordered
fallback behavior so existing HDFC files continue to work. HDFC savings
supports PDF, XLS, and XLSX; HDFC credit cards currently support PDF.

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
