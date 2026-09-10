"""
1099-DA Reconciliation Engine.

Matches 1099-DA form entries against calculated disposals to identify
discrepancies and generate actionable guidance for US tax filers.

Matching logic:
  1. Same asset (case-insensitive)
  2. Same date (±1 day tolerance)
  3. Proceeds within 2% tolerance for EXACT, 5% for FUZZY

CRITICAL: All monetary values use decimal.Decimal - NEVER float.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Optional

from src.importers.form_1099da import Form1099DAEntry
from src.calculator.lots import Disposal


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class MatchConfidence(Enum):
    EXACT = "exact"        # date + asset + proceeds all match
    FUZZY = "fuzzy"        # date ±1 day OR proceeds within 5%
    UNMATCHED = "unmatched"


class DiscrepancyType(Enum):
    MISSING_IMPORT = "missing_import"        # on 1099 but not in our data
    DEFI_NOT_ON_1099 = "defi_not_on_1099"    # in our data but not on 1099
    COST_BASIS_DIFF = "cost_basis_diff"
    PROCEEDS_DIFF = "proceeds_diff"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class Discrepancy:
    """A single discrepancy between 1099-DA and our calculated data."""
    type: DiscrepancyType
    description: str
    form_value: Optional[Decimal]
    our_value: Optional[Decimal]
    guidance: str  # "What to do" text


@dataclass
class MatchedEntry:
    """A matched pair: 1099-DA entry ↔ our disposal."""
    form_entry: Form1099DAEntry
    our_disposal: Disposal
    confidence: MatchConfidence
    discrepancies: list[Discrepancy] = field(default_factory=list)


@dataclass
class ReconciliationResult:
    """Complete reconciliation output."""
    matched: list[MatchedEntry]
    unmatched_1099: list[Form1099DAEntry]
    unmatched_ours: list[Disposal]
    discrepancies: list[Discrepancy]
    total_1099_proceeds: Decimal
    total_our_proceeds: Decimal
    match_rate: Decimal  # percentage matched (0-100)
    summary_text: str


# ---------------------------------------------------------------------------
# Matching helpers
# ---------------------------------------------------------------------------

def _normalize_asset(asset: str) -> str:
    """Normalize asset symbol for comparison."""
    return asset.strip().upper()


def _dates_match_exact(d1: date, d2: date) -> bool:
    """Check if two dates are the same."""
    return d1 == d2


def _dates_match_fuzzy(d1: date, d2: date, tolerance_days: int = 1) -> bool:
    """Check if two dates are within tolerance."""
    return abs((d1 - d2).days) <= tolerance_days


def _proceeds_match_exact(p1: Decimal, p2: Decimal, tolerance_pct: Decimal = Decimal("0.02")) -> bool:
    """Check if proceeds match within tolerance percentage (default 2%)."""
    if p1 == Decimal("0") and p2 == Decimal("0"):
        return True
    if p1 == Decimal("0") or p2 == Decimal("0"):
        return False
    diff_pct = abs(p1 - p2) / max(abs(p1), abs(p2))
    return diff_pct <= tolerance_pct


def _proceeds_match_fuzzy(p1: Decimal, p2: Decimal, tolerance_pct: Decimal = Decimal("0.05")) -> bool:
    """Check if proceeds match within fuzzy tolerance (default 5%)."""
    return _proceeds_match_exact(p1, p2, tolerance_pct)


def _disposal_date(disposal: Disposal) -> date:
    """Extract date from a Disposal (which stores datetime)."""
    if hasattr(disposal.date, "date"):
        return disposal.date.date()
    return disposal.date


# ---------------------------------------------------------------------------
# Guidance text generators
# ---------------------------------------------------------------------------

def _guidance_missing_import(broker: str) -> str:
    return (
        f"This transaction appears on your 1099-DA from {broker} but not in "
        f"your imported data. Import your {broker} transactions to resolve."
    )


def _guidance_defi_not_on_1099() -> str:
    return (
        "This DeFi transaction is not reported on any 1099-DA. "
        "You must self-report it on Form 8949."
    )


def _guidance_cost_basis_diff(form_value: Decimal, our_value: Decimal) -> str:
    return (
        f"Your 1099-DA shows cost basis of ${form_value:,.2f} but we calculated "
        f"${our_value:,.2f}. This may be due to transfers between wallets "
        f"affecting lot ordering."
    )


def _guidance_proceeds_diff(diff: Decimal) -> str:
    return (
        f"Proceeds differ by ${abs(diff):,.2f}. This is typically due to "
        f"rounding or fee treatment differences."
    )


# ---------------------------------------------------------------------------
# Core reconciliation engine
# ---------------------------------------------------------------------------

def reconcile(
    form_entries: list[Form1099DAEntry],
    our_disposals: list[Disposal],
) -> ReconciliationResult:
    """
    Reconcile 1099-DA form entries against our calculated disposals.

    Matching priority:
      1. EXACT: same asset + same date + proceeds within 2%
      2. FUZZY: same asset + date ±1 day + proceeds within 5%
      3. UNMATCHED: no match found

    Returns a ReconciliationResult with matched pairs, unmatched entries
    on both sides, discrepancies, and summary statistics.
    """
    matched: list[MatchedEntry] = []
    all_discrepancies: list[Discrepancy] = []

    # Track which disposals have been claimed
    available_disposals = list(our_disposals)

    # Track unmatched 1099 entries
    unmatched_1099: list[Form1099DAEntry] = []

    for form_entry in form_entries:
        best_match: Optional[Disposal] = None
        best_confidence = MatchConfidence.UNMATCHED
        best_index = -1

        form_asset = _normalize_asset(form_entry.asset)
        form_date = form_entry.date_sold
        form_proceeds = form_entry.proceeds

        for idx, disposal in enumerate(available_disposals):
            disp_asset = _normalize_asset(disposal.token)
            disp_date = _disposal_date(disposal)
            disp_proceeds = disposal.proceeds_usd

            # Must be same asset
            if form_asset != disp_asset:
                continue

            # Check EXACT match first
            if (_dates_match_exact(form_date, disp_date) and
                    _proceeds_match_exact(form_proceeds, disp_proceeds)):
                best_match = disposal
                best_confidence = MatchConfidence.EXACT
                best_index = idx
                break  # exact is best possible

            # Check FUZZY match
            if (_dates_match_fuzzy(form_date, disp_date) and
                    _proceeds_match_fuzzy(form_proceeds, disp_proceeds)):
                if best_confidence != MatchConfidence.EXACT:
                    best_match = disposal
                    best_confidence = MatchConfidence.FUZZY
                    best_index = idx

        if best_match is not None and best_index >= 0:
            # Remove from available pool
            available_disposals.pop(best_index)

            # Check for discrepancies within matched pair
            entry_discrepancies: list[Discrepancy] = []

            # Check cost basis difference
            if form_entry.cost_basis is not None and best_match.cost_basis_usd is not None:
                if not _proceeds_match_exact(form_entry.cost_basis, best_match.cost_basis_usd):
                    disc = Discrepancy(
                        type=DiscrepancyType.COST_BASIS_DIFF,
                        description=(
                            f"Cost basis mismatch for {form_asset}: "
                            f"1099-DA=${form_entry.cost_basis:,.2f}, "
                            f"ours=${best_match.cost_basis_usd:,.2f}"
                        ),
                        form_value=form_entry.cost_basis,
                        our_value=best_match.cost_basis_usd,
                        guidance=_guidance_cost_basis_diff(
                            form_entry.cost_basis, best_match.cost_basis_usd
                        ),
                    )
                    entry_discrepancies.append(disc)
                    all_discrepancies.append(disc)

            # Check proceeds difference (even in fuzzy matches)
            proceeds_diff = form_entry.proceeds - best_match.proceeds_usd
            if abs(proceeds_diff) > Decimal("0.01"):
                disc = Discrepancy(
                    type=DiscrepancyType.PROCEEDS_DIFF,
                    description=(
                        f"Proceeds differ for {form_asset}: "
                        f"1099-DA=${form_entry.proceeds:,.2f}, "
                        f"ours=${best_match.proceeds_usd:,.2f}"
                    ),
                    form_value=form_entry.proceeds,
                    our_value=best_match.proceeds_usd,
                    guidance=_guidance_proceeds_diff(proceeds_diff),
                )
                entry_discrepancies.append(disc)
                all_discrepancies.append(disc)

            matched.append(MatchedEntry(
                form_entry=form_entry,
                our_disposal=best_match,
                confidence=best_confidence,
                discrepancies=entry_discrepancies,
            ))
        else:
            # No match found - missing import
            unmatched_1099.append(form_entry)
            disc = Discrepancy(
                type=DiscrepancyType.MISSING_IMPORT,
                description=(
                    f"{form_asset} sold on {form_entry.date_sold} for "
                    f"${form_entry.proceeds:,.2f} appears on 1099-DA from "
                    f"{form_entry.broker_name} but not in your imported data."
                ),
                form_value=form_entry.proceeds,
                our_value=None,
                guidance=_guidance_missing_import(form_entry.broker_name),
            )
            all_discrepancies.append(disc)

    # Remaining disposals = DeFi/self-custody not on any 1099
    unmatched_ours: list[Disposal] = available_disposals
    for disposal in unmatched_ours:
        disc = Discrepancy(
            type=DiscrepancyType.DEFI_NOT_ON_1099,
            description=(
                f"{_normalize_asset(disposal.token)} disposed on "
                f"{_disposal_date(disposal)} for ${disposal.proceeds_usd:,.2f} "
                f"is not reported on any 1099-DA."
            ),
            form_value=None,
            our_value=disposal.proceeds_usd,
            guidance=_guidance_defi_not_on_1099(),
        )
        all_discrepancies.append(disc)

    # Compute summary statistics
    total_1099 = sum((e.proceeds for e in form_entries), Decimal("0"))
    total_ours = sum((d.proceeds_usd for d in our_disposals), Decimal("0"))

    total_entries = len(form_entries)
    match_rate = (
        (Decimal(len(matched)) / Decimal(total_entries) * Decimal("100"))
        if total_entries > 0
        else Decimal("100")
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # Build summary text
    summary_lines = [
        f"Reconciliation Summary",
        f"=" * 40,
        f"Total 1099-DA entries:     {len(form_entries)}",
        f"Total calculated disposals: {len(our_disposals)}",
        f"",
        f"Matched (exact):           {sum(1 for m in matched if m.confidence == MatchConfidence.EXACT)}",
        f"Matched (fuzzy):           {sum(1 for m in matched if m.confidence == MatchConfidence.FUZZY)}",
        f"Unmatched on 1099-DA:      {len(unmatched_1099)}",
        f"Unmatched in our data:     {len(unmatched_ours)}",
        f"",
        f"Match rate:                {match_rate}%",
        f"",
        f"Total 1099-DA proceeds:    ${total_1099:,.2f}",
        f"Total our proceeds:        ${total_ours:,.2f}",
        f"Difference:                ${abs(total_1099 - total_ours):,.2f}",
        f"",
        f"Discrepancies found:       {len(all_discrepancies)}",
    ]

    if unmatched_1099:
        summary_lines.append("")
        summary_lines.append("ACTION NEEDED: Import missing transactions")
        brokers = set(e.broker_name for e in unmatched_1099)
        for broker in sorted(brokers):
            count = sum(1 for e in unmatched_1099 if e.broker_name == broker)
            summary_lines.append(f"  - {broker}: {count} unmatched transaction(s)")

    if unmatched_ours:
        summary_lines.append("")
        summary_lines.append("ACTION NEEDED: Self-report DeFi disposals on Form 8949")
        summary_lines.append(
            f"  - {len(unmatched_ours)} disposal(s) not on any 1099-DA"
        )

    return ReconciliationResult(
        matched=matched,
        unmatched_1099=unmatched_1099,
        unmatched_ours=unmatched_ours,
        discrepancies=all_discrepancies,
        total_1099_proceeds=total_1099,
        total_our_proceeds=total_ours,
        match_rate=match_rate,
        summary_text="\n".join(summary_lines),
    )
