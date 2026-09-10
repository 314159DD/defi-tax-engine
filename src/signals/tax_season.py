"""
Tax season signal generator for community notifications.

Generates JSON signal files that can be sent to a community `#tax-tips` channel.
Signal format matches the internal signal spec.

Usage:
    python -m src.signals.tax_season                   # print all current signals
    python -m src.signals.tax_season --output signals/ # write to directory
    python -m src.signals.tax_season --check-deadlines # only emit urgent deadline signals
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Signal builder
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_signal(
    title: str,
    summary: str,
    data: dict[str, Any],
    confidence: float = 1.0,
) -> dict[str, Any]:
    return {
        "source": "crypto_tax",
        "title": title,
        "summary": summary,
        "confidence": round(confidence, 2),
        "data": data,
        "timestamp": _now_iso(),
    }


# ---------------------------------------------------------------------------
# Individual signal generators
# ---------------------------------------------------------------------------

def deadline_countdown_signal(days_until: int, deadline_label: str, deadline_date: date) -> dict | None:
    """
    Emit a deadline reminder signal when within 30 days.
    Returns None if the deadline is more than 30 days away or already passed.
    """
    if days_until < 0 or days_until > 30:
        return None

    if days_until == 0:
        urgency = "today"
    elif days_until <= 3:
        urgency = f"in {days_until} day{'s' if days_until > 1 else ''} - file NOW"
    elif days_until <= 7:
        urgency = f"in {days_until} days this week"
    else:
        urgency = f"in {days_until} days"

    return _build_signal(
        title=f"{deadline_label}: {urgency.capitalize()}",
        summary=(
            f"The {deadline_label} deadline is {urgency} ({deadline_date.strftime('%B %d, %Y')}). "
            "Export your crypto tax report now to avoid penalties."
        ),
        data={
            "type": "deadline",
            "deadline_label": deadline_label,
            "date": deadline_date.isoformat(),
            "days_remaining": days_until,
        },
        confidence=1.0,
    )


def irs_1099_da_signal(tax_year: int) -> dict:
    """
    Educational signal about IRS 1099-DA reporting requirements.
    New requirement for the 2026 tax year (brokers report to IRS directly).
    """
    return _build_signal(
        title=f"New IRS 1099-DA Requirements for {tax_year} Tax Year",
        summary=(
            f"Starting with the {tax_year} tax year, exchanges and brokers are required to report "
            "crypto transactions directly to the IRS via Form 1099-DA. "
            "Ensure your records match what your exchange reports - discrepancies can trigger audits. "
            "CryptoTax DeFi tracks which of your disposals are broker-reported vs self-reported."
        ),
        data={
            "type": "education",
            "topic": "1099-DA",
            "effective_tax_year": tax_year,
            "action": "review_broker_reported_disposals",
        },
        confidence=1.0,
    )


def harvest_opportunity_signal(
    unrealized_losses: Decimal,
    top_tokens: list[dict[str, Any]],
) -> dict:
    """
    Signal for tax loss harvesting opportunities.
    Only emit if unrealized losses are meaningful (> $100).
    """
    if unrealized_losses < Decimal("100"):
        return _build_signal(
            title="Tax Loss Harvesting: No Major Opportunities",
            summary=(
                "Your portfolio has minimal unrealized losses right now. "
                "Check back after significant market moves for harvesting opportunities."
            ),
            data={
                "type": "harvest",
                "unrealized_losses_usd": str(unrealized_losses),
                "opportunities": [],
            },
            confidence=0.8,
        )

    tokens_summary = ", ".join(
        f"{t['symbol']} ({t['unrealized_loss_usd']})" for t in top_tokens[:3]
    )
    return _build_signal(
        title=f"Tax Loss Harvesting Opportunity: ~${float(unrealized_losses):,.0f} Available",
        summary=(
            f"You have approximately ${float(unrealized_losses):,.2f} in unrealized losses "
            f"that could be harvested to offset gains. "
            f"Top candidates: {tokens_summary}. "
            "Sell and repurchase after 30+ days to avoid wash sale concerns."
        ),
        data={
            "type": "harvest",
            "unrealized_losses_usd": str(unrealized_losses),
            "opportunities": top_tokens,
        },
        confidence=0.85,
    )


# ---------------------------------------------------------------------------
# Main: compute and emit all relevant signals for current date
# ---------------------------------------------------------------------------

def generate_all_signals(year: int | None = None) -> list[dict]:
    """
    Generate all tax season signals relevant to the current date.
    Returns a list of signal dicts ready to serialize as JSON.
    """
    today = date.today()
    current_year = year or today.year
    signals: list[dict] = []

    # --- Deadline signals ---
    deadlines = [
        ("Tax Filing Deadline", date(current_year, 4, 15)),
        ("Q1 Estimated Tax Payment", date(current_year, 4, 15)),
        ("Q2 Estimated Tax Payment", date(current_year, 6, 16)),
        ("Q3 Estimated Tax Payment", date(current_year, 9, 15)),
        ("Tax Extension Deadline", date(current_year, 10, 15)),
        ("Q4 Estimated Tax Payment", date(current_year + 1, 1, 15)),
    ]

    for label, d in deadlines:
        days = (d - today).days
        sig = deadline_countdown_signal(days, label, d)
        if sig:
            signals.append(sig)

    # --- IRS 1099-DA educational signal (always relevant, emit once) ---
    # 1099-DA is effective for the 2026 tax year
    if current_year >= 2026:
        signals.append(irs_1099_da_signal(current_year))

    # --- Harvest opportunity signal (placeholder - real data from DB) ---
    # In production, this would query the harvest advisor for live data.
    # For now, generate a placeholder signal that the scheduler can replace.
    signals.append(
        harvest_opportunity_signal(
            unrealized_losses=Decimal("0"),
            top_tokens=[],
        )
    )

    return signals


def write_signals(signals: list[dict], output_dir: str | Path) -> list[Path]:
    """Write each signal to a JSON file in output_dir. Returns written paths."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for sig in signals:
        # Filename: <source>_<type>_<slug>_<timestamp>.json
        sig_type = sig["data"].get("type", "signal")
        slug = sig["title"].lower().replace(" ", "-").replace(":", "")[:40]
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        filename = out / f"crypto_tax_{sig_type}_{slug}_{ts}.json"
        filename.write_text(json.dumps(sig, indent=2))
        written.append(filename)

    return written


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate tax season signal files."
    )
    parser.add_argument("--output", "-o", default=None, help="Directory to write signal JSON files")
    parser.add_argument("--year", type=int, default=None, help="Tax year (default: current year)")
    parser.add_argument(
        "--check-deadlines",
        action="store_true",
        help="Only emit signals for upcoming deadlines (within 30 days)",
    )
    args = parser.parse_args()

    signals = generate_all_signals(year=args.year)

    if args.check_deadlines:
        signals = [s for s in signals if s["data"].get("type") == "deadline"]

    if not signals:
        print("No signals to emit for current date.")
        return

    if args.output:
        paths = write_signals(signals, args.output)
        for p in paths:
            print(f"Written: {p}")
    else:
        print(json.dumps(signals, indent=2))


if __name__ == "__main__":
    main()
