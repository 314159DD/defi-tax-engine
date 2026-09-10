"""
US ordinary income report for crypto.

Adapted from src/reports/income_report.py to work with income event objects/dicts.

Taxable income event types (IRS treatment):
  - staking rewards  -> ordinary income at FMV on date of receipt
  - airdrop          -> ordinary income at FMV on date of receipt
  - mining/validator -> ordinary income at FMV on date of receipt
  - interest         -> ordinary income

Reported on Schedule 1 (Additional Income), NOT Schedule D.
"""
from __future__ import annotations

import csv
import io
from decimal import Decimal


_CATEGORY_LABEL = {
    "reward": "Staking Reward",
    "airdrop": "Airdrop",
    "mining": "Mining Income",
    "validator": "Validator Income",
    "interest": "DeFi Interest",
}


def generate_income_csv(
    income_events: list,
    year: int,
) -> str:
    """
    Generate income CSV from income event objects.

    Args:
        income_events: list of income event dicts/objects with fields:
            date, tx_type, token, amount, usd_value, tx_hash, chain
        year: tax year to filter

    Returns:
        CSV string for income reporting
    """
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Date", "Type", "Category", "Chain", "Token", "Amount",
        "USD Value (FMV at Receipt)", "TX Hash",
    ])

    for e in income_events:
        # Support both dict and object access
        if isinstance(e, dict):
            e_date = e.get("date", "")
            e_type = e.get("tx_type", "")
            e_token = e.get("token", "")
            e_amount = e.get("amount", "0")
            e_usd = e.get("usd_value", "0")
            e_hash = e.get("tx_hash", "")
            e_chain = e.get("chain", "")
        else:
            e_date = getattr(e, "date", "")
            e_type = getattr(e, "tx_type", "")
            e_token = getattr(e, "token", "")
            e_amount = getattr(e, "amount", "0")
            e_usd = getattr(e, "usd_value", "0")
            e_hash = getattr(e, "tx_hash", "")
            e_chain = getattr(e, "chain", "")

        # Filter by year
        date_str = str(e_date)[:4]
        if date_str != str(year):
            continue

        writer.writerow([
            str(e_date)[:10],
            e_type,
            _CATEGORY_LABEL.get(e_type, str(e_type).title()),
            e_chain,
            e_token,
            str(e_amount),
            str(e_usd),
            e_hash,
        ])

    return output.getvalue()
