"""
1099-DA Reconciliation Report Generator.

Produces CSV and text summary reports from ReconciliationResult data.

CRITICAL: All monetary values use decimal.Decimal - NEVER float.
"""
from __future__ import annotations

import csv
import io
from decimal import Decimal

from src.tax.us.reconciliation import (
    DiscrepancyType,
    MatchConfidence,
    ReconciliationResult,
)


# ---------------------------------------------------------------------------
# CSV report
# ---------------------------------------------------------------------------

_CSV_COLUMNS = [
    "Status",
    "Asset",
    "Date",
    "1099-DA Proceeds",
    "Our Proceeds",
    "1099-DA Cost Basis",
    "Our Cost Basis",
    "Discrepancy",
    "Guidance",
]


def generate_reconciliation_csv(result: ReconciliationResult) -> str:
    """
    Generate a reconciliation report as CSV.

    Columns:
      Status, Asset, Date, 1099-DA Proceeds, Our Proceeds,
      1099-DA Cost Basis, Our Cost Basis, Discrepancy, Guidance
    """
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(_CSV_COLUMNS)

    # Matched entries
    for entry in result.matched:
        form = entry.form_entry
        disp = entry.our_disposal
        disp_date = disp.date.date() if hasattr(disp.date, "date") else disp.date

        status = f"Matched ({entry.confidence.value})"

        discrepancy_text = ""
        guidance_text = ""
        if entry.discrepancies:
            discrepancy_text = "; ".join(d.description for d in entry.discrepancies)
            guidance_text = "; ".join(d.guidance for d in entry.discrepancies)

        writer.writerow([
            status,
            form.asset,
            form.date_sold.isoformat(),
            _fmt_decimal(form.proceeds),
            _fmt_decimal(disp.proceeds_usd),
            _fmt_decimal(form.cost_basis) if form.cost_basis is not None else "",
            _fmt_decimal(disp.cost_basis_usd),
            discrepancy_text,
            guidance_text,
        ])

    # Unmatched 1099-DA entries
    for form in result.unmatched_1099:
        writer.writerow([
            "Missing Import",
            form.asset,
            form.date_sold.isoformat(),
            _fmt_decimal(form.proceeds),
            "",
            _fmt_decimal(form.cost_basis) if form.cost_basis is not None else "",
            "",
            f"On 1099-DA from {form.broker_name} but not in imported data",
            f"Import your {form.broker_name} transactions to resolve.",
        ])

    # Unmatched our disposals (DeFi)
    for disp in result.unmatched_ours:
        disp_date = disp.date.date() if hasattr(disp.date, "date") else disp.date
        writer.writerow([
            "DeFi / Not on 1099",
            disp.token,
            disp_date.isoformat(),
            "",
            _fmt_decimal(disp.proceeds_usd),
            "",
            _fmt_decimal(disp.cost_basis_usd),
            "Not reported on any 1099-DA",
            "Self-report on Form 8949.",
        ])

    return output.getvalue()


# ---------------------------------------------------------------------------
# Text summary report
# ---------------------------------------------------------------------------

def generate_reconciliation_summary(result: ReconciliationResult) -> str:
    """
    Generate a human-readable reconciliation summary.

    Includes the main summary text plus detailed discrepancy listing.
    """
    lines: list[str] = []

    # Main summary
    lines.append(result.summary_text)
    lines.append("")

    # Detailed discrepancy listing
    if result.discrepancies:
        lines.append("")
        lines.append("Detailed Discrepancies")
        lines.append("-" * 40)

        for i, disc in enumerate(result.discrepancies, 1):
            lines.append(f"")
            lines.append(f"  {i}. [{disc.type.value}] {disc.description}")
            if disc.form_value is not None:
                lines.append(f"     1099-DA value: ${disc.form_value:,.2f}")
            if disc.our_value is not None:
                lines.append(f"     Our value:     ${disc.our_value:,.2f}")
            lines.append(f"     Guidance: {disc.guidance}")

    # Matched entries summary table
    if result.matched:
        lines.append("")
        lines.append("")
        lines.append("Matched Transactions")
        lines.append("-" * 40)

        for entry in result.matched:
            form = entry.form_entry
            disp = entry.our_disposal
            tag = "EXACT" if entry.confidence == MatchConfidence.EXACT else "FUZZY"
            lines.append(
                f"  [{tag}] {form.asset}  {form.date_sold}  "
                f"1099=${form.proceeds:,.2f}  ours=${disp.proceeds_usd:,.2f}"
            )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_decimal(value: Decimal | None) -> str:
    """Format a Decimal as a string with 2 decimal places."""
    if value is None:
        return ""
    return f"{value:.2f}"
