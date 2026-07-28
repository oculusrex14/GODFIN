"""Generate a synthetic, redacted HDFC-style statement for E2E tests."""

from __future__ import annotations

import sys
from pathlib import Path

from fpdf import FPDF


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: generate_redacted_statement.py OUTPUT.pdf")

    output = Path(sys.argv[1]).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    pdf = FPDF()
    pdf.set_title("Synthetic GODFIN statement fixture")
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.cell(0, 10, "Statement of Account - Synthetic Test Data", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, "Savings Account XXXX0000", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    pdf.cell(
        0,
        8,
        "15/07/2026 SYNTHETIC UNKNOWN MERCHANT 450.00",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.cell(
        0,
        8,
        "16/07/2026 UPI-SYNTHETIC CAFE-cafe@upi-000000000001 275.00",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.output(str(output))


if __name__ == "__main__":
    main()
