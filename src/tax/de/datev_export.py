"""
DATEV CSV export.

Generates a CSV in standard DATEV Buchungssatz format for import into
DATEV accounting software (used by most German Steuerberater).

Standard DATEV format columns:
  Umsatz, Soll/Haben-Kennzeichen, Konto, Gegenkonto,
  Buchungstext, Belegdatum
"""
from __future__ import annotations

import csv
import io
from datetime import datetime
from decimal import Decimal

from src.tax.models import HoldingPeriod


def _fmt_date_datev(dt) -> str:
    """Format date as DDMM (DATEV short format for Belegdatum)."""
    if isinstance(dt, datetime):
        return dt.strftime("%d%m")
    if isinstance(dt, str):
        try:
            return datetime.fromisoformat(dt[:10]).strftime("%d%m")
        except (ValueError, TypeError):
            return ""
    if hasattr(dt, "strftime"):
        return dt.strftime("%d%m")
    return ""


def _fmt_eur_datev(amount: Decimal) -> str:
    """Format as DATEV currency: comma as decimal separator, no thousands."""
    return f"{abs(amount):.2f}".replace(".", ",")


def generate_datev_csv(
    disposals: list,
    year: int,
) -> str:
    """
    Generate DATEV Buchungssatz CSV from Disposal objects.

    Uses standard SKR03 accounts:
      - Konto 2740: Veraeusserungsgewinne aus privaten Geschaeften
      - Konto 2750: Veraeusserungsverluste aus privaten Geschaeften
      - Gegenkonto 1800: Bank (or 1200 for crypto-specific ledger)

    Args:
        disposals: list of Disposal objects
        year: tax year to filter

    Returns:
        DATEV-compatible CSV string (semicolon-delimited, ANSI encoding expected)
    """
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")

    # DATEV header row
    writer.writerow([
        "Umsatz (ohne Soll/Haben-Kz)",
        "Soll/Haben-Kennzeichen",
        "Konto",
        "Gegenkonto (ohne BU-Schluessel)",
        "BU-Schluessel",
        "Belegdatum",
        "Belegfeld 1",
        "Buchungstext",
    ])

    for d in disposals:
        if not hasattr(d.date, "year") or d.date.year != year:
            continue

        gain = d.gain_loss_usd
        description = f"Krypto {d.token} {d.amount:.6f}".rstrip("0").rstrip(".")

        if gain >= Decimal("0"):
            # Gain: credit to Veraeusserungsgewinne
            konto = "2740"
            gegenkonto = "1800"
            soll_haben = "H"  # Haben (credit)
        else:
            # Loss: debit to Veraeusserungsverluste
            konto = "2750"
            gegenkonto = "1800"
            soll_haben = "S"  # Soll (debit)

        writer.writerow([
            _fmt_eur_datev(gain),
            soll_haben,
            konto,
            gegenkonto,
            "",  # BU-Schluessel (empty)
            _fmt_date_datev(d.date),
            d.tx_hash[:8] if d.tx_hash else "",  # Belegfeld 1 (reference)
            description,
        ])

    return output.getvalue()
