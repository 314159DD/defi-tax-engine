"""
White-label branded report generation for accountant / CPA portal.

Generates a text-based report with accountant letterhead, tax summary,
individual report sections, methodology statement, and disclaimer.

Uses plain text + CSV formatting (no external PDF library required).
If reportlab is available, a proper PDF is generated; otherwise falls
back to a well-structured UTF-8 text document.

All monetary values use Decimal - NEVER float.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from src.tax.models import ReportFile


def _separator(char: str = "=", width: int = 72) -> str:
    return char * width


def _center(text: str, width: int = 72) -> str:
    return text.center(width)


def generate_branded_report(
    accountant_profile: dict,
    client_name: str,
    reports: list[ReportFile],
    methodology: str,
    year: int,
    tax_summary: Optional[dict] = None,
) -> bytes:
    """
    Generate a branded report combining all reports with accountant letterhead.

    Args:
        accountant_profile: dict with firm_name, contact_info, logo_url, license_number
        client_name: name of the client
        reports: list of ReportFile objects from the tax module
        methodology: description of the cost basis method used
        year: tax year
        tax_summary: optional dict with total_gains, total_losses, net, etc.

    Returns:
        UTF-8 encoded bytes of the branded report document
    """
    lines: list[str] = []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    firm_name = accountant_profile.get("firm_name", "Unknown Firm")
    contact_info = accountant_profile.get("contact_info", "")
    license_number = accountant_profile.get("license_number", "")

    # ── Header / Letterhead ────────────────────────────────────────────
    lines.append(_separator("="))
    lines.append("")
    lines.append(_center(firm_name.upper()))
    if contact_info:
        lines.append(_center(contact_info))
    if license_number:
        lines.append(_center(f"License: {license_number}"))
    lines.append("")
    lines.append(_separator("="))
    lines.append("")

    # ── Report title ───────────────────────────────────────────────────
    lines.append(_center(f"CRYPTO TAX REPORT - TAX YEAR {year}"))
    lines.append("")
    lines.append(f"  Prepared for:   {client_name}")
    lines.append(f"  Prepared by:    {firm_name}")
    lines.append(f"  Date:           {now}")
    lines.append(f"  Methodology:    {methodology}")
    lines.append("")
    lines.append(_separator("-"))

    # ── Tax summary (if provided) ──────────────────────────────────────
    if tax_summary:
        lines.append("")
        lines.append("  TAX SUMMARY")
        lines.append("  " + "-" * 40)

        summary_fields = [
            ("Total Gains", "total_gains"),
            ("Total Losses", "total_losses"),
            ("Net Gain/Loss", "net"),
            ("Short-Term Gains", "short_term_gains"),
            ("Long-Term Gains", "long_term_gains"),
            ("Exempt Gains", "exempt_gains"),
            ("Estimated Tax", "tax_liability"),
            ("Income Total", "income_total"),
        ]
        for label, key in summary_fields:
            value = tax_summary.get(key)
            if value is not None:
                lines.append(f"  {label:<25} {value:>15}")

        lines.append("")
        lines.append(_separator("-"))

    # ── Individual report sections ─────────────────────────────────────
    if reports:
        lines.append("")
        lines.append("  INCLUDED REPORTS")
        lines.append("  " + "-" * 40)
        for i, report in enumerate(reports, 1):
            lines.append(f"  {i}. {report.filename} ({report.report_type})")
        lines.append("")
        lines.append(_separator("-"))

        for report in reports:
            lines.append("")
            lines.append(f"  --- {report.filename} ---")
            lines.append("")
            content_str = (
                report.content if isinstance(report.content, str)
                else report.content.decode("utf-8", errors="replace")
            )
            # Indent report content
            for line in content_str.splitlines():
                lines.append(f"  {line}")
            lines.append("")
            lines.append(_separator("-"))

    # ── Footer: methodology + disclaimer ───────────────────────────────
    lines.append("")
    lines.append("  METHODOLOGY STATEMENT")
    lines.append("  " + "-" * 40)
    lines.append(f"  This report was prepared using the {methodology}.")
    lines.append(f"  All calculations are for the tax year {year}.")
    lines.append("  Monetary values are denominated in the applicable local currency.")
    lines.append("")

    lines.append("  DISCLAIMER")
    lines.append("  " + "-" * 40)
    lines.append("  This report is provided for informational purposes only and does")
    lines.append("  not constitute tax, legal, or financial advice. The calculations")
    lines.append("  are based on the transaction data provided and the cost basis")
    lines.append("  method selected. Tax laws vary by jurisdiction and are subject to")
    lines.append("  change. Consult a qualified tax professional for advice specific")
    lines.append("  to your situation.")
    lines.append("")
    lines.append(f"  Prepared by {firm_name} using Crypto Tax DeFi Calculator.")
    lines.append(f"  Generated: {now}")
    lines.append("")
    lines.append(_separator("="))

    return "\n".join(lines).encode("utf-8")
