"""
Anlage SO (Sonstige Einkuenfte) CSV generator.

Generates a CSV file formatted for use with German tax filing software
and Steuerberater (tax advisors).

Structure:
  Section 1: Private Veraeusserungsgeschaefte (§23 EStG) - crypto disposals
  Section 2: Sonstige Einkuenfte (§22 Nr. 3 EStG) - staking rewards, etc.

Columns for disposals:
  Zeile, Art des Wirtschaftsguts, Anschaffungsdatum, Veraeusserungsdatum,
  Veraeusserungspreis, Anschaffungskosten, Gewinn/Verlust
"""
from __future__ import annotations

import csv
import io
from datetime import datetime
from decimal import Decimal

from src.tax.models import HoldingPeriod


def _fmt_date_de(dt) -> str:
    """Format date as DD.MM.YYYY (German convention)."""
    if isinstance(dt, datetime):
        return dt.strftime("%d.%m.%Y")
    if isinstance(dt, str):
        try:
            return datetime.fromisoformat(dt[:10]).strftime("%d.%m.%Y")
        except (ValueError, TypeError):
            return dt
    if hasattr(dt, "strftime"):
        return dt.strftime("%d.%m.%Y")
    return str(dt)


def _fmt_eur(amount: Decimal) -> str:
    """Format Decimal as German currency string: 1234,56"""
    return f"{amount:.2f}".replace(".", ",")


def _is_short_term(d) -> bool:
    hp = d.holding_period
    if isinstance(hp, HoldingPeriod):
        return hp == HoldingPeriod.SHORT_TERM
    return str(hp) in ("short-term", "short", "SHORT_TERM")


def generate_anlage_so_csv(
    disposals: list,
    income_events: list,
    year: int,
) -> str:
    """
    Generate Anlage SO CSV.

    Args:
        disposals: list of Disposal objects
        income_events: list of income event dicts/objects
        year: tax year

    Returns:
        CSV string in Anlage SO format
    """
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")

    # --- Section 1: Private Veraeusserungsgeschaefte (§23 EStG) ---
    writer.writerow(["Anlage SO - Private Veraeusserungsgeschaefte (Kryptowaehrungen)"])
    writer.writerow([f"Steuerjahr: {year}"])
    writer.writerow([])

    writer.writerow([
        "Zeile",
        "Art des Wirtschaftsguts",
        "Anschaffungsdatum",
        "Veraeusserungsdatum",
        "Veraeusserungspreis (EUR)",
        "Anschaffungskosten (EUR)",
        "Gewinn/Verlust (EUR)",
        "Haltefrist",
        "Steuerpflichtig",
    ])

    zeile = 1
    total_taxable_gain = Decimal("0")
    total_exempt_gain = Decimal("0")

    for d in disposals:
        if not hasattr(d.date, "year") or d.date.year != year:
            continue

        is_short = _is_short_term(d)
        hp = d.holding_period
        if isinstance(hp, HoldingPeriod):
            is_exempt = hp == HoldingPeriod.EXEMPT
        else:
            is_exempt = str(hp) == "exempt"

        haltefrist = "<=365 Tage" if is_short else ">365 Tage (steuerfrei)"
        steuerpflichtig = "Ja" if is_short else "Nein"

        if is_short:
            total_taxable_gain += d.gain_loss_usd
        else:
            total_exempt_gain += d.gain_loss_usd

        description = f"{d.amount:.8f} {d.token}".rstrip("0").rstrip(".")

        writer.writerow([
            zeile,
            description,
            "Verschiedene",  # VARIOUS - multiple lot dates
            _fmt_date_de(d.date),
            _fmt_eur(d.proceeds_usd),
            _fmt_eur(d.cost_basis_usd),
            _fmt_eur(d.gain_loss_usd),
            haltefrist,
            steuerpflichtig,
        ])
        zeile += 1

    writer.writerow([])
    writer.writerow(["", "Summe steuerpflichtig", "", "", "", "", _fmt_eur(total_taxable_gain)])
    writer.writerow(["", "Summe steuerfrei (Spekulationsfrist)", "", "", "", "", _fmt_eur(total_exempt_gain)])

    # --- Section 2: Sonstige Einkuenfte (§22 Nr. 3 EStG) ---
    writer.writerow([])
    writer.writerow([])
    writer.writerow(["Sonstige Einkuenfte aus Kryptowaehrungen (\u00a722 Nr. 3 EStG)"])
    writer.writerow([])
    writer.writerow([
        "Zeile",
        "Art der Einkuenfte",
        "Datum",
        "Token",
        "Menge",
        "Wert (EUR)",
    ])

    total_income = Decimal("0")
    zeile = 1

    for e in income_events:
        if isinstance(e, dict):
            e_date = e.get("date", "")
            e_type = e.get("tx_type", "")
            e_token = e.get("token", "")
            e_amount = e.get("amount", "0")
            e_usd = e.get("usd_value", Decimal("0"))
        else:
            e_date = getattr(e, "date", "")
            e_type = getattr(e, "tx_type", "")
            e_token = getattr(e, "token", "")
            e_amount = getattr(e, "amount", "0")
            e_usd = getattr(e, "usd_value", Decimal("0"))

        date_str = str(e_date)[:4]
        if date_str != str(year):
            continue

        usd_val = Decimal(str(e_usd)) if not isinstance(e_usd, Decimal) else e_usd
        total_income += usd_val

        _TYPE_LABELS = {
            "reward": "Staking Reward",
            "airdrop": "Airdrop",
            "mining": "Mining",
            "validator": "Validator",
            "interest": "DeFi-Zinsen",
        }

        writer.writerow([
            zeile,
            _TYPE_LABELS.get(e_type, str(e_type)),
            _fmt_date_de(e_date),
            e_token,
            str(e_amount),
            _fmt_eur(usd_val),
        ])
        zeile += 1

    writer.writerow([])
    writer.writerow(["", "Summe Sonstige Einkuenfte", "", "", "", _fmt_eur(total_income)])

    return output.getvalue()
