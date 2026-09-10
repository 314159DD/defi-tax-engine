"""
Ordinary income report for crypto.

Taxable income event types (IRS treatment):
  - staking rewards  → ordinary income at FMV on date of receipt
  - airdrop          → ordinary income at FMV on date of receipt
  - mining / validator → ordinary income at FMV on date of receipt
  - interest         → ordinary income

These are reported on Schedule 1 (Additional Income), NOT Schedule D.
"""
from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

from src.storage.database import Database

_INCOME_TX_TYPES = frozenset({"reward", "airdrop", "mining", "validator", "interest"})

_CATEGORY_LABEL = {
    "reward": "Staking Reward",
    "airdrop": "Airdrop",
    "mining": "Mining Income",
    "validator": "Validator Income",
    "interest": "DeFi Interest",
}


@dataclass
class IncomeEvent:
    date: str           # ISO timestamp
    tx_type: str
    token: str
    amount: Decimal
    usd_value: Decimal  # FMV on date of receipt
    tx_hash: str
    chain: str


@dataclass
class IncomeSummary:
    year: int
    total_staking: Decimal
    total_airdrop: Decimal
    total_mining: Decimal
    total_interest: Decimal
    total_income: Decimal
    events: list[IncomeEvent]

    def as_dict(self) -> dict:
        return {
            "year": self.year,
            "total_staking_usd": str(self.total_staking),
            "total_airdrop_usd": str(self.total_airdrop),
            "total_mining_usd": str(self.total_mining),
            "total_interest_usd": str(self.total_interest),
            "total_income_usd": str(self.total_income),
            "event_count": len(self.events),
        }


class IncomeReportGenerator:
    """Generates ordinary income report from transaction records."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def generate(self, year: int) -> IncomeSummary:
        events = self._load_income_events(year)

        total_staking = Decimal("0")
        total_airdrop = Decimal("0")
        total_mining = Decimal("0")
        total_interest = Decimal("0")

        for e in events:
            if e.tx_type == "reward":
                total_staking += e.usd_value
            elif e.tx_type == "airdrop":
                total_airdrop += e.usd_value
            elif e.tx_type in ("mining", "validator"):
                total_mining += e.usd_value
            elif e.tx_type == "interest":
                total_interest += e.usd_value

        total = total_staking + total_airdrop + total_mining + total_interest

        return IncomeSummary(
            year=year,
            total_staking=total_staking,
            total_airdrop=total_airdrop,
            total_mining=total_mining,
            total_interest=total_interest,
            total_income=total,
            events=events,
        )

    def _load_income_events(self, year: int) -> list[IncomeEvent]:
        """Query transactions table for income-type events in the given year."""
        events: list[IncomeEvent] = []
        with self._db.connect() as conn:
            rows = conn.execute(
                """
                SELECT tx_hash, chain, timestamp, tx_type, raw_json
                FROM transactions
                WHERE tx_type IN ('reward','airdrop','mining','validator','interest')
                  AND timestamp LIKE ?
                ORDER BY timestamp
                """,
                (f"{year}%",),
            ).fetchall()

        for row in rows:
            raw = json.loads(row["raw_json"]) if row["raw_json"] else {}
            assets_in = raw.get("assets_in", [])
            for asset in assets_in:
                amount = Decimal(str(asset.get("amount", "0")))
                usd_value = Decimal(str(asset.get("usd_value") or "0"))
                events.append(IncomeEvent(
                    date=row["timestamp"],
                    tx_type=row["tx_type"],
                    token=asset.get("token_symbol", "UNKNOWN"),
                    amount=amount,
                    usd_value=usd_value,
                    tx_hash=row["tx_hash"],
                    chain=row["chain"],
                ))

        return events

    def to_csv(self, year: int) -> str:
        summary = self.generate(year)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Date", "Type", "Category", "Chain", "Token", "Amount",
            "USD Value (FMV at Receipt)", "TX Hash",
        ])
        for e in summary.events:
            writer.writerow([
                e.date[:10],
                e.tx_type,
                _CATEGORY_LABEL.get(e.tx_type, e.tx_type.title()),
                e.chain,
                e.token,
                str(e.amount),
                str(e.usd_value),
                e.tx_hash,
            ])
        return output.getvalue()

    def print_report(self, year: int) -> str:
        s = self.generate(year)
        lines = [
            f"Ordinary Income Report - {year}",
            "=" * 50,
            f"  Staking Rewards:  ${s.total_staking:>12,.2f}",
            f"  Airdrops:         ${s.total_airdrop:>12,.2f}",
            f"  Mining/Validator: ${s.total_mining:>12,.2f}",
            f"  DeFi Interest:    ${s.total_interest:>12,.2f}",
            "-" * 50,
            f"  TOTAL INCOME:     ${s.total_income:>12,.2f}",
            "",
            f"  ({len(s.events)} income events)",
        ]
        return "\n".join(lines)
